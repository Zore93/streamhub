"""StreamHub backend - FastAPI app."""
import asyncio
import logging
import os
import random
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Header,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware

from auth import (
    JWT_SECRET,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from mailer import send_verification_email
from storage import (
    upload_file as wasabi_upload,
    wasabi_configured,
    test_connection as wasabi_test,
    presign_get_url,
)
import hashlib
import hmac
import time
import urllib.parse
import subprocess
from collections import defaultdict, deque
from models import (
    Announcement,
    AppSettings,
    BanReq,
    Category,
    Comment,
    CommentReq,
    LoginReq,
    Package,
    PaymentTransaction,
    RegisterReq,
    StatsResponse,
    User,
    UserPublic,
    Video,
    VideoRendition,
    VideoUpdateReq,
    new_id,
    now_iso,
)
from transcoder import (
    RESOLUTIONS,
    filter_resolutions_for_source,
    generate_thumbnails,
    probe_video,
    transcode_to_resolution,
)

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/app/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
(UPLOAD_DIR / "videos").mkdir(exist_ok=True)
(UPLOAD_DIR / "thumbnails").mkdir(exist_ok=True)
(UPLOAD_DIR / "avatars").mkdir(exist_ok=True)
(UPLOAD_DIR / "covers").mkdir(exist_ok=True)
(UPLOAD_DIR / "originals").mkdir(exist_ok=True)
(UPLOAD_DIR / "subtitles").mkdir(exist_ok=True)

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="StreamHub API")
api = APIRouter(prefix="/api")

# Serve uploaded media at /uploads/* (we route through /api/media/* for ingress)
# Mount under app so it can be accessed
app.mount("/api/media", StaticFiles(directory=str(UPLOAD_DIR)), name="media")

logger = logging.getLogger("streamhub")
logging.basicConfig(level=logging.INFO)


# ============ Concurrency semaphore (recreated when settings change) ============
class TranscodeQueue:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(2)
        self.concurrency = 2

    def set_concurrency(self, n: int):
        if n < 1:
            n = 1
        if n != self.concurrency:
            self.concurrency = n
            self.semaphore = asyncio.Semaphore(n)


queue = TranscodeQueue()


# ============ Rate limiting (in-memory; per-IP+email login) ============
_login_attempts: dict[str, deque] = defaultdict(deque)


def _rate_limit_check(key: str, max_attempts: int, window: int):
    now = time.time()
    dq = _login_attempts[key]
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= max_attempts:
        raise HTTPException(429, f"Too many login attempts. Try again in {window} seconds.")


def _rate_limit_record(key: str):
    _login_attempts[key].append(time.time())


def _rate_limit_reset(key: str):
    _login_attempts.pop(key, None)


def _validate_password(pw: str, settings: dict):
    min_len = int(settings.get("min_password_length", 8))
    if len(pw) < min_len:
        raise HTTPException(400, f"Password must be at least {min_len} characters")
    if settings.get("require_password_complexity", True):
        has_letter = any(c.isalpha() for c in pw)
        has_digit = any(c.isdigit() for c in pw)
        has_symbol = any(not c.isalnum() for c in pw)
        if not (has_letter and has_digit and has_symbol):
            raise HTTPException(
                400,
                "Password must contain letters, digits and at least one symbol",
            )


# ============ Helpers ============
async def get_settings() -> dict:
    s = await db.settings.find_one({"_id": "main"}, {"_id": 0})
    if not s:
        s = AppSettings().model_dump()
        await db.settings.insert_one({"_id": "main", **s})
    return s


async def save_settings(s: dict):
    await db.settings.update_one({"_id": "main"}, {"$set": s}, upsert=True)


def public_user(u: dict) -> dict:
    if not u:
        return None
    return UserPublic(**u).model_dump()


def media_url(request: Request, rel_path: str) -> str:
    """Build absolute URL like https://.../api/media/<rel>"""
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/media/{rel_path.lstrip('/')}"


def _sign_local(rel_path: str, exp: int) -> str:
    msg = f"{rel_path}|{exp}".encode("utf-8")
    return hmac.new(JWT_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def signed_local_url(request: Request, rel_path: str, ttl_seconds: int) -> str:
    exp = int(time.time()) + int(ttl_seconds)
    sig = _sign_local(rel_path, exp)
    base = str(request.base_url).rstrip("/")
    safe_path = urllib.parse.quote(rel_path, safe="/")
    return f"{base}/api/secure-media/{safe_path}?exp={exp}&sig={sig}"


async def maybe_sign_url(
    request: Request, url: str, settings: dict, ttl_seconds: int
) -> str:
    """Returns a signed/presigned variant of the given stored URL."""
    if url.startswith("http://") or url.startswith("https://"):
        signed = await presign_get_url(url, settings, ttl_seconds)
        return signed or url
    return signed_local_url(request, url, ttl_seconds)


async def current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> Optional[dict]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    user_id = decode_token(authorization.split(" ", 1)[1])
    if not user_id:
        return None
    u = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not u:
        return None
    # Check ban
    if u.get("banned_until"):
        bu = u["banned_until"]
        if bu == "permanent":
            raise HTTPException(403, "Account banned permanently")
        try:
            until = datetime.fromisoformat(bu)
            if until > datetime.now(timezone.utc):
                raise HTTPException(403, f"Account banned until {bu}")
        except ValueError:
            pass
    return u


async def require_user(user: Optional[dict] = Depends(current_user)) -> dict:
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


async def require_admin(user: dict = Depends(require_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s).strip().lower()
    return re.sub(r"[\s-]+", "-", s) or new_id()[:8]


# ============ Background transcode task ============
async def process_video(video_id: str, src_path: str):
    settings = await get_settings()
    queue.set_concurrency(int(settings.get("ffmpeg_concurrency", 2)))
    async with queue.semaphore:
        try:
            await db.videos.update_one(
                {"id": video_id}, {"$set": {"status": "processing", "progress": 5}}
            )
            info = await probe_video(src_path)
            duration = info["duration"]
            src_h = info["height"]
            src_w = info["width"]
            await db.videos.update_one(
                {"id": video_id},
                {
                    "$set": {
                        "duration_sec": duration,
                        "original_width": src_w,
                        "original_height": src_h,
                        "progress": 15,
                    }
                },
            )
            # Generate 10 thumbnails
            thumb_dir = UPLOAD_DIR / "thumbnails"
            thumbs = await generate_thumbnails(
                src_path, str(thumb_dir), video_id, duration, 10
            )
            use_wasabi = wasabi_configured(settings)
            thumb_urls: List[str] = []
            for tp in thumbs:
                rel = f"thumbnails/{Path(tp).name}"
                if use_wasabi:
                    url = await wasabi_upload(tp, rel, settings, "image/jpeg")
                    if url:
                        thumb_urls.append(url)
                        try:
                            os.remove(tp)
                        except Exception:
                            pass
                    else:
                        thumb_urls.append(rel)  # fallback local
                else:
                    thumb_urls.append(rel)
            await db.videos.update_one(
                {"id": video_id},
                {
                    "$set": {
                        "thumbnail_options": thumb_urls,
                        "thumbnail_url": thumb_urls[0] if thumb_urls else None,
                        "progress": 30,
                    }
                },
            )
            # Decide which resolutions
            enabled = settings.get("enabled_resolutions", ["360p", "720p", "1080p"])
            target_resolutions = filter_resolutions_for_source(src_h or 1080, enabled)
            renditions: List[dict] = []
            total = max(len(target_resolutions), 1)
            for i, res in enumerate(target_resolutions):
                out_rel = f"videos/{video_id}_{res}.mp4"
                out_path = UPLOAD_DIR / out_rel
                ok = await transcode_to_resolution(src_path, str(out_path), res)
                if ok:
                    w, h = RESOLUTIONS[res]
                    final_url = out_rel
                    if use_wasabi:
                        uploaded = await wasabi_upload(
                            str(out_path), out_rel, settings, "video/mp4"
                        )
                        if uploaded:
                            final_url = uploaded
                            try:
                                os.remove(out_path)
                            except Exception:
                                pass
                    renditions.append(
                        VideoRendition(
                            resolution=res, url=final_url, width=w, height=h
                        ).model_dump()
                    )
                progress = 30 + int(65 * (i + 1) / total)
                await db.videos.update_one(
                    {"id": video_id},
                    {"$set": {"renditions": renditions, "progress": progress}},
                )
            await db.videos.update_one(
                {"id": video_id},
                {"$set": {"status": "ready", "progress": 100}},
            )
            # Cleanup original file regardless of storage backend
            try:
                os.remove(src_path)
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            logger.exception("transcode failed")
            await db.videos.update_one(
                {"id": video_id},
                {"$set": {"status": "failed", "error": str(e)}},
            )


# ============ AUTH ============
@api.post("/auth/register")
async def register(req: RegisterReq, request: Request):
    settings = await get_settings()
    _validate_password(req.password, settings)
    if await db.users.find_one({"email": req.email.lower()}):
        raise HTTPException(400, "Email already registered")
    if await db.users.find_one({"username": req.username}):
        raise HTTPException(400, "Username taken")
    require_verify = bool(settings.get("require_email_verification", False))
    verify_token = secrets.token_urlsafe(32) if require_verify else None
    u = User(
        email=req.email.lower(),
        username=req.username,
        password_hash=hash_password(req.password),
        role="user",
        email_verified=not require_verify,
        verify_token=verify_token,
    )
    await db.users.insert_one(u.model_dump())
    if require_verify and verify_token:
        base = str(request.base_url).rstrip("/")
        verify_url = f"{base}/verify-email?token={verify_token}"
        await send_verification_email(settings, u.email, verify_url)
        return {"message": "Verification email sent", "require_verification": True}
    token = create_token(u.id)
    return {"token": token, "user": public_user(u.model_dump())}


@api.post("/auth/login")
async def login(req: LoginReq, request: Request):
    settings = await get_settings()
    rate_key = f"{request.client.host if request.client else 'unknown'}|{req.email.lower()}"
    _rate_limit_check(
        rate_key,
        int(settings.get("login_rate_limit_max", 5)),
        int(settings.get("login_rate_limit_window", 300)),
    )
    u = await db.users.find_one({"email": req.email.lower()}, {"_id": 0})
    if not u or not verify_password(req.password, u["password_hash"]):
        _rate_limit_record(rate_key)
        raise HTTPException(401, "Invalid credentials")
    if not u.get("email_verified"):
        raise HTTPException(403, "Email not verified. Check your inbox.")
    if u.get("banned_until"):
        bu = u["banned_until"]
        if bu == "permanent":
            raise HTTPException(403, "Account banned permanently")
        try:
            if datetime.fromisoformat(bu) > datetime.now(timezone.utc):
                raise HTTPException(403, f"Account banned until {bu}")
        except ValueError:
            pass
    # Check pro expiry
    if u.get("is_pro") and u.get("pro_expires_at"):
        try:
            if datetime.fromisoformat(u["pro_expires_at"]) < datetime.now(timezone.utc):
                await db.users.update_one({"id": u["id"]}, {"$set": {"is_pro": False}})
                u["is_pro"] = False
        except ValueError:
            pass
    token = create_token(u["id"])
    _rate_limit_reset(rate_key)
    return {"token": token, "user": public_user(u)}


@api.get("/auth/me")
async def me(user: dict = Depends(require_user)):
    return public_user(user)


@api.get("/auth/verify")
async def verify_email(token: str):
    u = await db.users.find_one({"verify_token": token}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Invalid token")
    await db.users.update_one(
        {"id": u["id"]},
        {"$set": {"email_verified": True, "verify_token": None}},
    )
    return {"message": "Email verified! You can now log in."}


# ============ USERS / PROFILE ============
@api.get("/users/{user_id}")
async def get_user(user_id: str):
    u = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Not found")
    return public_user(u)


@api.patch("/users/me")
async def update_profile(
    bio: Optional[str] = Form(None),
    user: dict = Depends(require_user),
):
    upd = {}
    if bio is not None:
        upd["bio"] = bio
    if upd:
        await db.users.update_one({"id": user["id"]}, {"$set": upd})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return public_user(u)


@api.post("/users/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...), user: dict = Depends(require_user)
):
    ext = (Path(file.filename or "img").suffix or ".jpg").lower()
    fname = f"{user['id']}_avatar{ext}"
    out_path = UPLOAD_DIR / "avatars" / fname
    with open(out_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = f"avatars/{fname}"
    settings = await get_settings()
    if wasabi_configured(settings):
        url = await wasabi_upload(str(out_path), rel, settings)
        if url:
            rel = url
            try:
                out_path.unlink()
            except Exception:
                pass
    await db.users.update_one({"id": user["id"]}, {"$set": {"avatar_url": rel}})
    return {"avatar_url": rel}


@api.post("/users/me/cover")
async def upload_cover(
    file: UploadFile = File(...), user: dict = Depends(require_user)
):
    ext = (Path(file.filename or "img").suffix or ".jpg").lower()
    fname = f"{user['id']}_cover{ext}"
    out_path = UPLOAD_DIR / "covers" / fname
    with open(out_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = f"covers/{fname}"
    settings = await get_settings()
    if wasabi_configured(settings):
        url = await wasabi_upload(str(out_path), rel, settings)
        if url:
            rel = url
            try:
                out_path.unlink()
            except Exception:
                pass
    await db.users.update_one({"id": user["id"]}, {"$set": {"cover_url": rel}})
    return {"cover_url": rel}


@api.get("/users/{user_id}/videos")
async def user_videos(user_id: str):
    vids = (
        await db.videos.find({"uploader_id": user_id}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(200)
    )
    return vids


# ============ CATEGORIES ============
@api.get("/categories")
async def list_categories():
    cats = await db.categories.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    return cats


@api.post("/categories")
async def create_category(payload: dict, admin: dict = Depends(require_admin)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    slug = slugify(name)
    if await db.categories.find_one({"slug": slug}):
        raise HTTPException(400, "Category exists")
    c = Category(name=name, slug=slug)
    await db.categories.insert_one(c.model_dump())
    return c.model_dump()


@api.delete("/categories/{cat_id}")
async def delete_category(cat_id: str, admin: dict = Depends(require_admin)):
    await db.categories.delete_one({"id": cat_id})
    return {"ok": True}


# ============ VIDEOS ============
@api.get("/videos")
async def list_videos(
    section: str = "latest",
    category_id: Optional[str] = None,
    limit: int = 20,
):
    q = {"status": "ready"}
    if category_id:
        q["category_id"] = category_id
    if section == "popular":
        cur = db.videos.find(q, {"_id": 0}).sort("views", -1).limit(limit)
        return await cur.to_list(limit)
    if section == "random":
        # mongo sample
        pipeline = [{"$match": q}, {"$sample": {"size": limit}}, {"$project": {"_id": 0}}]
        return await db.videos.aggregate(pipeline).to_list(limit)
    # latest
    cur = db.videos.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cur.to_list(limit)


@api.get("/videos/{video_id}")
async def get_video(video_id: str, request: Request, user: Optional[dict] = Depends(current_user)):
    v = await db.videos.find_one({"id": video_id}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Not found")
    if v.get("access_tier") == "pro":
        if not user or not user.get("is_pro"):
            v["locked"] = True
            v["renditions"] = []
            v["subtitles"] = []
            return v
        settings = await get_settings()
        ttl = int(settings.get("signed_url_ttl_seconds", 300))
        signed_rends = []
        for r in v.get("renditions", []):
            r2 = dict(r)
            r2["url"] = await maybe_sign_url(request, r["url"], settings, ttl)
            signed_rends.append(r2)
        v["renditions"] = signed_rends
        signed_subs = []
        for s in v.get("subtitles", []):
            s2 = dict(s)
            s2["url"] = await maybe_sign_url(request, s["url"], settings, ttl)
            signed_subs.append(s2)
        v["subtitles"] = signed_subs
        v["signed"] = True
        v["signed_ttl"] = ttl
    return v


@api.post("/videos/{video_id}/view")
async def add_view(video_id: str):
    await db.videos.update_one({"id": video_id}, {"$inc": {"views": 1}})
    return {"ok": True}


@api.post("/videos/{video_id}/like")
async def toggle_like(video_id: str, user: dict = Depends(require_user)):
    v = await db.videos.find_one({"id": video_id}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Not found")
    likes = v.get("likes", [])
    if user["id"] in likes:
        likes.remove(user["id"])
        liked = False
    else:
        likes.append(user["id"])
        liked = True
    await db.videos.update_one({"id": video_id}, {"$set": {"likes": likes}})
    return {"liked": liked, "count": len(likes)}


@api.get("/videos/{video_id}/recommendations")
async def recommendations(video_id: str, limit: int = 15):
    v = await db.videos.find_one({"id": video_id}, {"_id": 0})
    q = {"status": "ready", "id": {"$ne": video_id}}
    if v and v.get("category_id"):
        # try same category first
        same = await db.videos.find(
            {**q, "category_id": v["category_id"]}, {"_id": 0}
        ).limit(limit).to_list(limit)
        if len(same) >= limit:
            return same
        # backfill with random others
        need = limit - len(same)
        exclude_ids = [video_id] + [x["id"] for x in same]
        extra = await db.videos.aggregate(
            [
                {"$match": {"status": "ready", "id": {"$nin": exclude_ids}}},
                {"$sample": {"size": need}},
                {"$project": {"_id": 0}},
            ]
        ).to_list(need)
        return same + extra
    pipeline = [{"$match": q}, {"$sample": {"size": limit}}, {"$project": {"_id": 0}}]
    return await db.videos.aggregate(pipeline).to_list(limit)


@api.post("/videos/upload")
async def upload_video(
    background: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    category_id: Optional[str] = Form(None),
    access_tier: str = Form("free"),
    user: dict = Depends(require_user),
):
    settings = await get_settings()
    if not settings.get("allow_user_uploads", True) and user.get("role") != "admin":
        raise HTTPException(403, "User uploads disabled by admin")
    max_mb = int(settings.get("max_upload_size_mb", 1024))
    # Save original
    vid_id = new_id()
    orig_ext = (Path(file.filename or "video.mp4").suffix or ".mp4").lower()
    src_path = UPLOAD_DIR / "originals" / f"{vid_id}{orig_ext}"
    size = 0
    with open(src_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_mb * 1024 * 1024:
                f.close()
                try:
                    src_path.unlink()
                except Exception:
                    pass
                raise HTTPException(413, f"File exceeds {max_mb} MB limit")
            f.write(chunk)
    tags_list = [t.strip() for t in tags.split(",") if t.strip()]
    if access_tier not in ("free", "pro"):
        access_tier = "free"
    v = Video(
        id=vid_id,
        title=title,
        description=description,
        tags=tags_list,
        category_id=category_id,
        uploader_id=user["id"],
        uploader_username=user["username"],
        access_tier=access_tier,
        original_filename=file.filename or "",
        original_size_bytes=size,
        status="processing",
    )
    await db.videos.insert_one(v.model_dump())
    # Schedule background
    background.add_task(process_video, vid_id, str(src_path))
    return v.model_dump()


@api.patch("/videos/{video_id}")
async def update_video(
    video_id: str, req: VideoUpdateReq, user: dict = Depends(require_user)
):
    v = await db.videos.find_one({"id": video_id}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Not found")
    if v["uploader_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your video")
    upd = {k: val for k, val in req.model_dump(exclude_unset=True).items() if val is not None}
    if upd:
        await db.videos.update_one({"id": video_id}, {"$set": upd})
    v = await db.videos.find_one({"id": video_id}, {"_id": 0})
    return v


@api.delete("/videos/{video_id}")
async def delete_video(video_id: str, user: dict = Depends(require_user)):
    v = await db.videos.find_one({"id": video_id}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Not found")
    if v["uploader_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not yours")
    settings = await get_settings()
    # cleanup files (local) - skip http urls (Wasabi)
    for r in v.get("renditions", []):
        url = r.get("url", "")
        if url.startswith("http"):
            await _delete_wasabi_url(url, settings)
        else:
            try:
                (UPLOAD_DIR / url).unlink()
            except Exception:
                pass
    for t in v.get("thumbnail_options", []):
        if t.startswith("http"):
            await _delete_wasabi_url(t, settings)
        else:
            try:
                (UPLOAD_DIR / t).unlink()
            except Exception:
                pass
    await db.videos.delete_one({"id": video_id})
    await db.comments.delete_many({"video_id": video_id})
    return {"ok": True}


async def _delete_wasabi_url(url: str, settings: dict):
    """Best-effort delete given a public URL."""
    if not wasabi_configured(settings):
        return
    # extract key after bucket
    bucket = settings.get("wasabi_bucket", "")
    if not bucket or bucket not in url:
        return
    key = url.split(bucket + "/", 1)[-1]
    try:
        import boto3
        from botocore.client import Config
        def _do():
            cli = boto3.client(
                "s3",
                endpoint_url=settings.get("wasabi_endpoint"),
                aws_access_key_id=settings.get("wasabi_access_key"),
                aws_secret_access_key=settings.get("wasabi_secret_key"),
                region_name=settings.get("wasabi_region") or "us-east-1",
                config=Config(signature_version="s3v4"),
            )
            cli.delete_object(Bucket=bucket, Key=key)
        await asyncio.to_thread(_do)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"wasabi delete failed: {e}")


# ============ COMMENTS ============
@api.get("/videos/{video_id}/comments")
async def list_comments(video_id: str):
    cs = await db.comments.find({"video_id": video_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return cs


@api.post("/videos/{video_id}/comments")
async def add_comment(
    video_id: str, req: CommentReq, user: dict = Depends(require_user)
):
    if not req.content.strip():
        raise HTTPException(400, "Empty content")
    c = Comment(
        video_id=video_id,
        user_id=user["id"],
        username=user["username"],
        avatar_url=user.get("avatar_url"),
        content=req.content.strip(),
    )
    await db.comments.insert_one(c.model_dump())
    return c.model_dump()


@api.delete("/comments/{comment_id}")
async def delete_comment(comment_id: str, user: dict = Depends(require_user)):
    c = await db.comments.find_one({"id": comment_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Not found")
    if c["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not allowed")
    await db.comments.delete_one({"id": comment_id})
    return {"ok": True}


# ============ PACKAGES ============
@api.get("/packages")
async def list_packages():
    pks = await db.packages.find({"active": True}, {"_id": 0}).sort("sort_order", 1).to_list(20)
    return pks


@api.get("/packages/all")
async def list_all_packages(admin: dict = Depends(require_admin)):
    pks = await db.packages.find({}, {"_id": 0}).sort("sort_order", 1).to_list(20)
    return pks


@api.post("/packages")
async def create_package(payload: dict, admin: dict = Depends(require_admin)):
    count = await db.packages.count_documents({})
    if count >= 10:
        raise HTTPException(400, "Max 10 packages allowed")
    p = Package(**payload)
    await db.packages.insert_one(p.model_dump())
    return p.model_dump()


@api.patch("/packages/{pkg_id}")
async def update_package(pkg_id: str, payload: dict, admin: dict = Depends(require_admin)):
    await db.packages.update_one({"id": pkg_id}, {"$set": payload})
    p = await db.packages.find_one({"id": pkg_id}, {"_id": 0})
    return p


@api.delete("/packages/{pkg_id}")
async def delete_package(pkg_id: str, admin: dict = Depends(require_admin)):
    await db.packages.delete_one({"id": pkg_id})
    return {"ok": True}


# ============ ANNOUNCEMENTS ============
@api.get("/announcements/active")
async def active_announcements():
    return await db.announcements.find({"active": True}, {"_id": 0}).sort("created_at", -1).to_list(20)


@api.get("/announcements")
async def all_announcements(admin: dict = Depends(require_admin)):
    return await db.announcements.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)


@api.post("/announcements")
async def create_announcement(payload: dict, admin: dict = Depends(require_admin)):
    a = Announcement(**payload)
    await db.announcements.insert_one(a.model_dump())
    return a.model_dump()


@api.patch("/announcements/{a_id}")
async def update_announcement(a_id: str, payload: dict, admin: dict = Depends(require_admin)):
    await db.announcements.update_one({"id": a_id}, {"$set": payload})
    return await db.announcements.find_one({"id": a_id}, {"_id": 0})


@api.delete("/announcements/{a_id}")
async def delete_announcement(a_id: str, admin: dict = Depends(require_admin)):
    await db.announcements.delete_one({"id": a_id})
    return {"ok": True}


# ============ ADMIN: SETTINGS ============
@api.get("/admin/settings")
async def admin_get_settings(admin: dict = Depends(require_admin)):
    return await get_settings()


@api.patch("/admin/settings")
async def admin_update_settings(payload: dict, admin: dict = Depends(require_admin)):
    cur = await get_settings()
    # whitelist keys
    allowed = set(AppSettings.model_fields.keys())
    upd = {k: v for k, v in payload.items() if k in allowed}
    cur.update(upd)
    await save_settings(cur)
    queue.set_concurrency(int(cur.get("ffmpeg_concurrency", 2)))
    return cur


@api.post("/admin/wasabi/test")
async def admin_test_wasabi(admin: dict = Depends(require_admin)):
    s = await get_settings()
    ok, msg = await wasabi_test(s)
    return {"ok": ok, "message": msg}


# ============ ADMIN: USERS ============
@api.get("/admin/users")
async def admin_list_users(admin: dict = Depends(require_admin)):
    us = await db.users.find({}, {"_id": 0, "password_hash": 0, "verify_token": 0}).sort("created_at", -1).to_list(500)
    return us


@api.post("/admin/users/{user_id}/ban")
async def admin_ban_user(user_id: str, req: BanReq, admin: dict = Depends(require_admin)):
    now = datetime.now(timezone.utc)
    if req.duration == "permanent":
        until = "permanent"
    elif req.duration == "1day":
        until = (now + timedelta(days=1)).isoformat()
    elif req.duration == "1week":
        until = (now + timedelta(days=7)).isoformat()
    elif req.duration == "1month":
        until = (now + timedelta(days=30)).isoformat()
    elif req.duration == "custom":
        until = (now + timedelta(days=int(req.custom_days or 1))).isoformat()
    else:
        raise HTTPException(400, "Invalid duration")
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"banned_until": until, "banned_reason": req.reason or ""}},
    )
    return {"ok": True, "banned_until": until}


@api.post("/admin/users/{user_id}/unban")
async def admin_unban(user_id: str, admin: dict = Depends(require_admin)):
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"banned_until": None, "banned_reason": None}},
    )
    return {"ok": True}


@api.post("/admin/users/{user_id}/grant-pro")
async def admin_grant_pro(user_id: str, payload: dict, admin: dict = Depends(require_admin)):
    """Grant PRO to a user for a chosen duration.

    Body: {duration: "1day|1week|1month|permanent|custom", custom_days?: int, package_id?: str}
    """
    duration = (payload.get("duration") or "1month").lower()
    now = datetime.now(timezone.utc)
    if duration == "permanent":
        expires = None  # treated as no expiry
        expires_iso = "permanent"
    elif duration == "1day":
        expires = now + timedelta(days=1)
        expires_iso = expires.isoformat()
    elif duration == "1week":
        expires = now + timedelta(days=7)
        expires_iso = expires.isoformat()
    elif duration == "1month":
        expires = now + timedelta(days=30)
        expires_iso = expires.isoformat()
    elif duration == "custom":
        expires = now + timedelta(days=int(payload.get("custom_days") or 1))
        expires_iso = expires.isoformat()
    else:
        raise HTTPException(400, "Invalid duration")
    upd = {"is_pro": True, "pro_expires_at": expires_iso}
    if payload.get("package_id"):
        upd["pro_package_id"] = payload["package_id"]
    await db.users.update_one({"id": user_id}, {"$set": upd})
    return {"ok": True, "pro_expires_at": expires_iso}


@api.post("/admin/users/{user_id}/revoke-pro")
async def admin_revoke_pro(user_id: str, admin: dict = Depends(require_admin)):
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"is_pro": False, "pro_expires_at": None, "pro_package_id": None}},
    )
    return {"ok": True}


@api.post("/admin/users/{user_id}/role")
async def admin_set_role(user_id: str, payload: dict, admin: dict = Depends(require_admin)):
    role = payload.get("role")
    if role not in ("user", "admin"):
        raise HTTPException(400, "invalid role")
    await db.users.update_one({"id": user_id}, {"$set": {"role": role}})
    return {"ok": True}


# ============ ADMIN: STATS ============
@api.get("/admin/stats", response_model=StatsResponse)
async def admin_stats(admin: dict = Depends(require_admin)):
    total_videos = await db.videos.count_documents({})
    total_users = await db.users.count_documents({})
    total_pro = await db.users.count_documents({"is_pro": True})
    total_comments = await db.comments.count_documents({})
    views_agg = await db.videos.aggregate(
        [{"$group": {"_id": None, "v": {"$sum": "$views"}}}]
    ).to_list(1)
    likes_agg = await db.videos.aggregate(
        [{"$project": {"c": {"$size": "$likes"}}}, {"$group": {"_id": None, "v": {"$sum": "$c"}}}]
    ).to_list(1)
    return StatsResponse(
        total_videos=total_videos,
        total_users=total_users,
        total_views=int(views_agg[0]["v"]) if views_agg else 0,
        total_pro_users=total_pro,
        total_likes=int(likes_agg[0]["v"]) if likes_agg else 0,
        total_comments=total_comments,
    )


@api.get("/admin/videos")
async def admin_list_videos(admin: dict = Depends(require_admin)):
    return await db.videos.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


# ============ STRIPE PAYMENTS ============
@api.post("/payments/checkout")
async def create_checkout(payload: dict, request: Request, user: dict = Depends(require_user)):
    pkg_id = payload.get("package_id")
    origin = payload.get("origin_url") or str(request.base_url).rstrip("/")
    pkg = await db.packages.find_one({"id": pkg_id, "active": True}, {"_id": 0})
    if not pkg:
        raise HTTPException(404, "Package not found")
    settings = await get_settings()
    api_key = settings.get("stripe_secret_key") or os.environ.get("STRIPE_API_KEY")
    if not api_key:
        raise HTTPException(500, "Stripe not configured")
    from emergentintegrations.payments.stripe.checkout import (
        StripeCheckout,
        CheckoutSessionRequest,
    )
    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=api_key, webhook_url=webhook_url)
    success_url = f"{origin}/pro/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/pro"
    req = CheckoutSessionRequest(
        amount=float(pkg["price"]),
        currency=pkg.get("currency", "usd"),
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "user_id": user["id"],
            "user_email": user["email"],
            "package_id": pkg["id"],
        },
    )
    session = await stripe_checkout.create_checkout_session(req)
    tx = PaymentTransaction(
        session_id=session.session_id,
        user_id=user["id"],
        user_email=user["email"],
        package_id=pkg["id"],
        amount=float(pkg["price"]),
        currency=pkg.get("currency", "usd"),
        metadata={"package_id": pkg["id"], "user_id": user["id"]},
    )
    await db.payment_transactions.insert_one(tx.model_dump())
    return {"url": session.url, "session_id": session.session_id}


@api.get("/payments/status/{session_id}")
async def payment_status(session_id: str, request: Request):
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")
    settings = await get_settings()
    api_key = settings.get("stripe_secret_key") or os.environ.get("STRIPE_API_KEY")
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    host_url = str(request.base_url)
    stripe_checkout = StripeCheckout(api_key=api_key, webhook_url=f"{host_url}api/webhook/stripe")
    status_resp = await stripe_checkout.get_checkout_status(session_id)
    new_payment_status = status_resp.payment_status
    new_status = status_resp.status
    # Only credit once
    if tx["payment_status"] != "paid" and new_payment_status == "paid":
        pkg = await db.packages.find_one({"id": tx["package_id"]}, {"_id": 0})
        days = int(pkg.get("duration_days", 30)) if pkg else 30
        expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        await db.users.update_one(
            {"id": tx["user_id"]},
            {"$set": {"is_pro": True, "pro_package_id": tx["package_id"], "pro_expires_at": expires_at}},
        )
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"payment_status": new_payment_status, "status": new_status, "updated_at": now_iso()}},
    )
    return {
        "payment_status": new_payment_status,
        "status": new_status,
        "amount": status_resp.amount_total,
        "currency": status_resp.currency,
    }


@api.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    settings = await get_settings()
    api_key = settings.get("stripe_secret_key") or os.environ.get("STRIPE_API_KEY")
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    host_url = str(request.base_url)
    stripe_checkout = StripeCheckout(api_key=api_key, webhook_url=f"{host_url}api/webhook/stripe")
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    resp = await stripe_checkout.handle_webhook(body, sig)
    if resp.session_id:
        tx = await db.payment_transactions.find_one({"session_id": resp.session_id}, {"_id": 0})
        if tx and tx["payment_status"] != "paid" and resp.payment_status == "paid":
            pkg = await db.packages.find_one({"id": tx["package_id"]}, {"_id": 0})
            days = int(pkg.get("duration_days", 30)) if pkg else 30
            expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
            await db.users.update_one(
                {"id": tx["user_id"]},
                {"$set": {"is_pro": True, "pro_package_id": tx["package_id"], "pro_expires_at": expires_at}},
            )
            await db.payment_transactions.update_one(
                {"session_id": resp.session_id},
                {"$set": {"payment_status": "paid", "updated_at": now_iso()}},
            )
    return {"ok": True}


# ============ GITHUB AUTO-UPDATE ============
def _detect_repo_path() -> str:
    """Try common locations for the host clone of this repo (when running in docker)."""
    for cand in ("/host_app", "/opt/streamhub", "/app"):
        if os.path.isdir(os.path.join(cand, ".git")):
            return cand
    return "/app"


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)


@api.get("/admin/github/check")
async def github_check(admin: dict = Depends(require_admin)):
    """Check whether a new commit is available on the configured branch."""
    settings = await get_settings()
    repo_path = _detect_repo_path()
    branch = settings.get("github_branch") or "main"
    # local commit
    r = _git(repo_path, "rev-parse", "HEAD")
    local_sha = r.stdout.strip() if r.returncode == 0 else None
    # try to read remote URL from git itself first (avoids needing repo URL setting)
    remote_url = ""
    r2 = _git(repo_path, "config", "--get", "remote.origin.url")
    if r2.returncode == 0:
        remote_url = r2.stdout.strip()
    if not remote_url:
        remote_url = settings.get("github_repo") or ""
    # fetch and compare
    fetch_ok = False
    if remote_url and local_sha:
        r3 = _git(repo_path, "fetch", "origin", branch)
        fetch_ok = r3.returncode == 0
    r4 = _git(repo_path, "rev-parse", f"origin/{branch}")
    remote_sha = r4.stdout.strip() if r4.returncode == 0 else None
    behind = 0
    if local_sha and remote_sha:
        r5 = _git(repo_path, "rev-list", "--count", f"{local_sha}..{remote_sha}")
        if r5.returncode == 0:
            try:
                behind = int(r5.stdout.strip())
            except ValueError:
                pass
    return {
        "repo_path": repo_path,
        "remote_url": remote_url,
        "branch": branch,
        "local_commit": (local_sha or "")[:12],
        "remote_commit": (remote_sha or "")[:12],
        "behind": behind,
        "has_update": bool(remote_sha and local_sha and remote_sha != local_sha),
        "fetched": fetch_ok,
    }


@api.post("/admin/github/update")
async def github_update(admin: dict = Depends(require_admin)):
    """Pull latest from origin and (best-effort) trigger a rebuild via docker.sock."""
    settings = await get_settings()
    repo_path = _detect_repo_path()
    branch = settings.get("github_branch") or "main"
    pull = _git(repo_path, "pull", "origin", branch)
    out = {"pull_rc": pull.returncode, "stdout": pull.stdout, "stderr": pull.stderr}
    # If docker socket is mounted in this container, kick off a rebuild
    if os.path.exists("/var/run/docker.sock"):
        compose_file = os.path.join(repo_path, "deploy/docker-compose.yml")
        env_file = os.path.join(repo_path, "deploy/.env")
        if os.path.exists(compose_file):
            r = subprocess.run(
                ["docker", "compose", "-f", compose_file, "--env-file", env_file,
                 "up", "-d", "--build"],
                capture_output=True, text=True, timeout=600,
            )
            out["rebuild_rc"] = r.returncode
            out["rebuild_stdout"] = r.stdout[-2000:]
            out["rebuild_stderr"] = r.stderr[-2000:]
    return out


# ============ STARTUP ============
@app.on_event("startup")
async def startup():
    # Ensure settings exist
    await get_settings()
    # Seed admin
    existing = await db.users.find_one({"email": "admin@streamhub.io"})
    if not existing:
        admin = User(
            email="admin@streamhub.io",
            username="admin",
            password_hash=hash_password("Admin123!"),
            role="admin",
            email_verified=True,
            is_pro=True,
        )
        await db.users.insert_one(admin.model_dump())
        logger.info("Seeded admin: admin@streamhub.local / Admin123!")
    # Seed default categories
    if await db.categories.count_documents({}) == 0:
        for name in ["Music", "Gaming", "Tech", "Education", "Comedy", "Travel"]:
            c = Category(name=name, slug=slugify(name))
            await db.categories.insert_one(c.model_dump())


@app.on_event("shutdown")
async def shutdown():
    client.close()


@api.get("/")
async def root():
    return {"message": "StreamHub API", "status": "ok"}


# ============ SUBTITLES ============
@api.post("/videos/{video_id}/subtitles")
async def add_subtitle(
    video_id: str,
    file: UploadFile = File(...),
    language: str = Form(...),
    label: str = Form(...),
    user: dict = Depends(require_user),
):
    v = await db.videos.find_one({"id": video_id}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Not found")
    if v["uploader_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your video")
    if len(v.get("subtitles", [])) >= 10:
        raise HTTPException(400, "Max 10 subtitles per video")
    ext = (Path(file.filename or "sub.srt").suffix or ".srt").lower()
    if ext not in (".srt", ".ass", ".vtt"):
        raise HTTPException(400, "Only .srt, .ass or .vtt allowed")
    sub_id = new_id()
    orig_name = f"{video_id}_{sub_id}{ext}"
    vtt_name = f"{video_id}_{sub_id}.vtt"
    orig_path = UPLOAD_DIR / "subtitles" / orig_name
    vtt_path = UPLOAD_DIR / "subtitles" / vtt_name
    if ext == ".vtt":
        # Uploaded file already IS WebVTT — write directly to vtt_path, no original.
        with open(vtt_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        rel_vtt = f"subtitles/{vtt_name}"
        rel_orig = None
    else:
        with open(orig_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(orig_path), str(vtt_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if not vtt_path.exists():
            raise HTTPException(500, "Subtitle conversion failed")
        rel_vtt = f"subtitles/{vtt_name}"
        rel_orig = f"subtitles/{orig_name}"
    settings = await get_settings()
    if wasabi_configured(settings):
        url_vtt = await wasabi_upload(str(vtt_path), rel_vtt, settings, "text/vtt")
        if url_vtt:
            rel_vtt = url_vtt
            try:
                vtt_path.unlink()
            except Exception:
                pass
        if rel_orig:
            url_orig = await wasabi_upload(str(orig_path), rel_orig, settings, "text/plain")
            if url_orig:
                rel_orig = url_orig
                try:
                    orig_path.unlink()
                except Exception:
                    pass
    from models import Subtitle as _Sub
    sub = _Sub(
        id=sub_id, language=language, label=label,
        url=rel_vtt, original_url=rel_orig, format=ext[1:],
    ).model_dump()
    await db.videos.update_one({"id": video_id}, {"$push": {"subtitles": sub}})
    return sub


@api.delete("/videos/{video_id}/subtitles/{sub_id}")
async def delete_subtitle(video_id: str, sub_id: str, user: dict = Depends(require_user)):
    v = await db.videos.find_one({"id": video_id}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Not found")
    if v["uploader_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not yours")
    subs = v.get("subtitles", [])
    target = next((s for s in subs if s["id"] == sub_id), None)
    if not target:
        raise HTTPException(404, "Subtitle not found")
    settings = await get_settings()
    for u in (target.get("url"), target.get("original_url")):
        if not u:
            continue
        if u.startswith("http"):
            await _delete_wasabi_url(u, settings)
        else:
            try:
                (UPLOAD_DIR / u).unlink()
            except Exception:
                pass
    await db.videos.update_one({"id": video_id}, {"$pull": {"subtitles": {"id": sub_id}}})
    return {"ok": True}


# ============ CONTACT ============
@api.post("/contact")
async def contact_form(payload: dict):
    title = (payload.get("title") or "").strip()
    message = (payload.get("message") or "").strip()
    email = (payload.get("email") or "").strip()
    if not title or not message or not email:
        raise HTTPException(400, "All fields required")
    settings = await get_settings()
    to = settings.get("contact_email")
    if not to:
        raise HTTPException(503, "Contact email not configured by admin")
    # Persist
    await db.contact_messages.insert_one({
        "id": new_id(), "title": title, "message": message, "email": email,
        "created_at": now_iso(),
    })
    # Best-effort send via SMTP
    if settings.get("smtp_enabled") and settings.get("smtp_host"):
        try:
            from email.message import EmailMessage
            import aiosmtplib
            msg = EmailMessage()
            msg["From"] = settings.get("smtp_from") or settings.get("smtp_user")
            msg["To"] = to
            msg["Reply-To"] = email
            msg["Subject"] = f"[StreamHub Contact] {title}"
            msg.set_content(f"From: {email}\n\n{message}")
            await aiosmtplib.send(
                msg,
                hostname=settings.get("smtp_host"),
                port=int(settings.get("smtp_port", 587)),
                username=settings.get("smtp_user") or None,
                password=settings.get("smtp_password") or None,
                start_tls=bool(settings.get("smtp_use_tls", True)),
                timeout=15,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"contact smtp failed: {e}")
    return {"ok": True}


@api.get("/admin/contact-messages")
async def admin_contact_messages(admin: dict = Depends(require_admin)):
    return await db.contact_messages.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.delete("/admin/contact-messages/{mid}")
async def admin_delete_contact_message(mid: str, admin: dict = Depends(require_admin)):
    await db.contact_messages.delete_one({"id": mid})
    return {"ok": True}


@api.get("/site/contact-config")
async def public_contact_config():
    s = await get_settings()
    return {"enabled": bool(s.get("contact_email"))}


@api.get("/site/player-config")
async def public_player_config():
    s = await get_settings()
    return {"allow_video_download": bool(s.get("allow_video_download", False))}


@api.get("/site/config")
async def public_site_config():
    """Public site identity / SEO config consumed by frontend index.html and Layout."""
    s = await get_settings()
    return {
        "title": s.get("site_title") or "StreamHub",
        "description": s.get("site_description") or "",
        "favicon_url": s.get("site_favicon_url") or "",
        "keywords": s.get("site_seo_keywords") or "",
        "meta": s.get("site_seo_meta") or "",
    }


@api.get("/secure-media/{rel_path:path}")
async def secure_media(rel_path: str, exp: int, sig: str):
    """Serve protected local media files with HMAC-signed URL validation."""
    if exp < int(time.time()):
        raise HTTPException(410, "URL expired")
    expected = _sign_local(rel_path, exp)
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(403, "Bad signature")
    full = UPLOAD_DIR / rel_path
    if not full.exists() or not str(full.resolve()).startswith(str(UPLOAD_DIR.resolve())):
        raise HTTPException(404, "Not found")
    return FileResponse(str(full))


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
