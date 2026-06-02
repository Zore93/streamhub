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
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from auth import (
    JWT_SECRET,
    create_token,
    decode_token,
    hash_password,
    set_jwt_secret,
    verify_password,
)
from mailer import send_contact_message, send_test_email, send_verification_email
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
    ChatBanReq,
    ChatMessage,
    ChatSendReq,
    Comment,
    CommentReq,
    GuestChatBan,
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
from chat import hub as chat_hub, video_status_hub
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
async def _publish_status(video_id: str) -> None:
    """Push the current minimal status snapshot to subscribed WebSocket clients."""
    doc = await db.videos.find_one(
        {"id": video_id},
        {"_id": 0, "status": 1, "progress": 1, "renditions": 1, "error": 1,
         "thumbnail_url": 1, "is_short": 1, "duration_sec": 1},
    )
    if doc:
        await video_status_hub.publish(video_id, doc)


async def process_video(video_id: str, src_path: str):
    settings = await get_settings()
    queue.set_concurrency(int(settings.get("ffmpeg_concurrency", 2)))
    async with queue.semaphore:
        try:
            await db.videos.update_one(
                {"id": video_id}, {"$set": {"status": "processing", "progress": 5}}
            )
            await _publish_status(video_id)
            info = await probe_video(src_path)
            duration = info["duration"]
            src_h = info["height"]
            src_w = info["width"]
            # Auto-detect shorts: vertical aspect AND under configured max duration.
            # The explicit `is_short=True` flag from the uploader always wins.
            cur_doc = await db.videos.find_one({"id": video_id}, {"_id": 0}) or {}
            already_short = bool(cur_doc.get("is_short"))
            max_short_dur = int(settings.get("shorts_max_duration_sec", 60))
            auto_short = (
                src_h > 0
                and src_w > 0
                and src_h > src_w
                and duration > 0
                and duration <= max_short_dur
            )
            is_short_final = already_short or auto_short
            await db.videos.update_one(
                {"id": video_id},
                {
                    "$set": {
                        "duration_sec": duration,
                        "original_width": src_w,
                        "original_height": src_h,
                        "is_short": is_short_final,
                        "progress": 15,
                    }
                },
            )
            await _publish_status(video_id)
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
            await _publish_status(video_id)
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
                # As soon as the FIRST rendition completes, mark the video "ready"
                # so the watch page can start playing while the rest transcode.
                upd = {"renditions": renditions, "progress": progress}
                if renditions and i == 0:
                    upd["status"] = "ready"
                await db.videos.update_one({"id": video_id}, {"$set": upd})
                await _publish_status(video_id)
            await db.videos.update_one(
                {"id": video_id},
                {"$set": {"status": "ready", "progress": 100}},
            )
            await _publish_status(video_id)
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
            await _publish_status(video_id)


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
    category_ids: Optional[str] = None,  # comma-separated; up to 2 — extra are ignored
    kind: Optional[str] = None,  # "video" (long) | "short" | None (all)
    access_tier: Optional[str] = None,  # "free" | "pro" | None (both)
    q: Optional[str] = None,  # case-insensitive title/tags search
    limit: int = 20,
    skip: int = 0,
):
    """List videos with optional filters used by the Discover page.

    `category_ids="abc,def"` selects videos in EITHER category (OR semantics, max 2).
    `q="naruto"` matches title OR tags case-insensitively.
    `access_tier="free"|"pro"` restricts to that tier.
    """
    filt: dict = {"status": "ready"}
    if category_id:
        filt["category_id"] = category_id
    elif category_ids:
        ids = [c.strip() for c in category_ids.split(",") if c.strip()][:2]
        if ids:
            filt["category_id"] = {"$in": ids}
    if kind == "short":
        filt["is_short"] = True
    elif kind == "video":
        filt["is_short"] = {"$ne": True}
    if access_tier in ("free", "pro"):
        filt["access_tier"] = access_tier
    if q:
        # Build an escaped regex so user input doesn't break Mongo
        import re as _re
        rex = _re.escape(q.strip())
        if rex:
            filt["$or"] = [
                {"title": {"$regex": rex, "$options": "i"}},
                {"tags": {"$regex": rex, "$options": "i"}},
            ]
    if section == "popular":
        cur = db.videos.find(filt, {"_id": 0}).sort("views", -1).skip(skip).limit(limit)
        return await cur.to_list(limit)
    if section == "random":
        pipeline = [{"$match": filt}, {"$sample": {"size": limit + skip}},
                    {"$project": {"_id": 0}}, {"$skip": skip}, {"$limit": limit}]
        return await db.videos.aggregate(pipeline).to_list(limit)
    cur = db.videos.find(filt, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    return await cur.to_list(limit)


@api.get("/videos/count")
async def count_videos(
    section: str = "latest",
    category_id: Optional[str] = None,
    kind: Optional[str] = None,
):
    q = {"status": "ready"}
    if category_id:
        q["category_id"] = category_id
    if kind == "short":
        q["is_short"] = True
    elif kind == "video":
        q["is_short"] = {"$ne": True}
    return {"count": await db.videos.count_documents(q)}


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
    is_short: bool = Form(False),
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
        is_short=is_short,
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
    # Subtitles update is reorder-only: caller may rearrange existing entries
    # but cannot inject new ones or alter URLs (those go through the dedicated
    # POST endpoint that performs ffmpeg conversion + storage upload).
    if "subtitles" in upd:
        existing_by_id = {s["id"]: s for s in (v.get("subtitles") or [])}
        rebuilt: list[dict] = []
        for item in upd["subtitles"]:
            if not isinstance(item, dict) or "id" not in item:
                raise HTTPException(400, "Subtitle item missing id")
            cur = existing_by_id.get(item["id"])
            if not cur:
                raise HTTPException(400, f"Unknown subtitle id {item['id']}")
            rebuilt.append(cur)
        # Must include every existing subtitle (no deletes via reorder)
        if {s["id"] for s in rebuilt} != set(existing_by_id):
            raise HTTPException(400, "Reorder must include all subtitles. Use DELETE to remove.")
        upd["subtitles"] = rebuilt
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
    allowed = set(AppSettings.model_fields.keys())
    upd = {k: v for k, v in payload.items() if k in allowed}
    # Type-validate by running the merged dict through AppSettings — anything
    # that can't be coerced raises 422 instead of being silently stored.
    try:
        merged = {**cur, **upd}
        AppSettings(**{k: merged[k] for k in allowed if k in merged})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"Invalid setting value: {e}")
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


@api.get("/admin/videos/legacy-stats")
async def admin_legacy_stats(admin: dict = Depends(require_admin)):
    """How many migrated (legacy_id present) videos exist, their is_short split,
    and their access-tier split."""
    base = {"legacy_id": {"$exists": True, "$ne": None}}
    total = await db.videos.count_documents(base)
    as_shorts = await db.videos.count_documents({**base, "is_short": True})
    as_pro = await db.videos.count_documents({**base, "access_tier": "pro"})
    return {
        "total_legacy": total,
        "legacy_as_shorts": as_shorts,
        "legacy_as_videos": total - as_shorts,
        "legacy_as_pro": as_pro,
        "legacy_as_free": total - as_pro,
    }


@api.post("/admin/videos/mark-legacy-as-shorts")
async def admin_mark_legacy_as_shorts(admin: dict = Depends(require_admin)):
    """Force `is_short=True` on every video that originated from the legacy
    migration (i.e. has a `legacy_id`).  Useful when the migrated catalogue is
    short-form by nature and the heuristic didn't have enough metadata
    (orientation/dimensions) to auto-detect it during parsing.
    """
    r = await db.videos.update_many(
        {"legacy_id": {"$exists": True, "$ne": None}},
        {"$set": {"is_short": True}},
    )
    return {"matched": r.matched_count, "modified": r.modified_count}


@api.post("/admin/videos/mark-legacy-as-videos")
async def admin_mark_legacy_as_videos(admin: dict = Depends(require_admin)):
    """Inverse of the above — moves all legacy items back to long-form video listings."""
    r = await db.videos.update_many(
        {"legacy_id": {"$exists": True, "$ne": None}},
        {"$set": {"is_short": False}},
    )
    return {"matched": r.matched_count, "modified": r.modified_count}


@api.post("/admin/videos/mark-legacy-as-pro")
async def admin_mark_legacy_as_pro(admin: dict = Depends(require_admin)):
    """Force `access_tier=pro` on every video that originated from the legacy
    migration (i.e. has a `legacy_id`).  Use this after a migration if you
    forgot the `--all-pro` flag on `parse_legacy_dump.py` and want to gate the
    whole legacy catalogue behind the PRO subscription."""
    r = await db.videos.update_many(
        {"legacy_id": {"$exists": True, "$ne": None}},
        {"$set": {"access_tier": "pro"}},
    )
    return {"matched": r.matched_count, "modified": r.modified_count}


@api.post("/admin/videos/mark-legacy-as-free")
async def admin_mark_legacy_as_free(admin: dict = Depends(require_admin)):
    """Inverse: open the entire legacy catalogue to free users."""
    r = await db.videos.update_many(
        {"legacy_id": {"$exists": True, "$ne": None}},
        {"$set": {"access_tier": "free"}},
    )
    return {"matched": r.matched_count, "modified": r.modified_count}


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
def _detect_repo_path() -> tuple[str, Optional[str]]:
    """Find a directory that contains a usable .git folder.

    Returns (path, error). When `error` is set, no .git was found in the
    candidate list and the caller should surface the diagnostic instead of
    blindly running git against /app.
    """
    candidates = ["/host_app", "/opt/streamhub", "/app"]
    for cand in candidates:
        if os.path.isdir(os.path.join(cand, ".git")):
            return cand, None
    return "/app", f"No .git directory found in any of: {', '.join(candidates)}"


def _git(cwd, *args):
    # `safe.directory=*` bypasses Git 2.35+ dubious-ownership rejection that
    # routinely fires when a docker container (uid 0) inspects a host bind-mount
    # owned by another uid.  Without it, every git call silently fails with
    # "fatal: detected dubious ownership in repository" and the UI shows "?".
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(
        ["git", "-c", "safe.directory=*", *args],
        cwd=cwd, capture_output=True, text=True, timeout=60, env=env,
    )


def _git_or_err(cwd, *args) -> tuple[str, str]:
    r = _git(cwd, *args)
    if r.returncode != 0:
        return "", (r.stderr or r.stdout or f"git {' '.join(args)} → rc={r.returncode}").strip()
    return r.stdout.strip(), ""


def _strip_token_from_url(url: str) -> str:
    """Return a copy of `url` with any embedded user:password@ removed."""
    if not url or "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    _creds, host_path = rest.rsplit("@", 1)
    return f"{scheme}://{host_path}"


@api.get("/admin/github/check")
async def github_check(admin: dict = Depends(require_admin)):
    """Check whether a new commit is available on the configured branch.

    Returns rich diagnostics on failure so the admin UI can surface the real
    git error (missing remote, network unreachable, dubious ownership, etc.)
    instead of silently displaying "?".
    """
    settings = await get_settings()
    repo_path, path_err = _detect_repo_path()
    branch = settings.get("github_branch") or "main"
    errors: list[str] = []
    if path_err:
        errors.append(path_err)

    # local commit
    local_sha, e = _git_or_err(repo_path, "rev-parse", "HEAD")
    if e:
        errors.append(f"rev-parse HEAD: {e}")

    # remote URL — prefer git's own config, fall back to admin setting only if
    # it looks like a real URL (avoids "x/y" garbage that used to be seeded).
    remote_url, _ = _git_or_err(repo_path, "config", "--get", "remote.origin.url")
    if not remote_url:
        setting_url = (settings.get("github_repo") or "").strip()
        if setting_url and ("://" in setting_url or setting_url.startswith("git@")):
            remote_url = setting_url

    # fetch (best effort)
    fetch_ok = False
    fetch_err = ""
    if remote_url and local_sha:
        r3 = _git(repo_path, "fetch", "origin", branch)
        fetch_ok = r3.returncode == 0
        if not fetch_ok:
            fetch_err = (r3.stderr or r3.stdout or "fetch failed").strip()
            errors.append(f"fetch origin {branch}: {fetch_err}")
    elif not remote_url:
        errors.append("No `remote.origin.url` configured — git clone the repo with HTTPS/SSH to /opt/streamhub first.")

    remote_sha, e = _git_or_err(repo_path, "rev-parse", f"origin/{branch}")
    if e and remote_url:
        # Only treat this as an error if we actually had a remote — otherwise the
        # missing ref is just a consequence of "no remote configured".
        errors.append(f"rev-parse origin/{branch}: {e}")

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
        "remote_url": _strip_token_from_url(remote_url),
        "branch": branch,
        "local_commit": (local_sha or "")[:12],
        "remote_commit": (remote_sha or "")[:12],
        "behind": behind,
        "has_update": bool(remote_sha and local_sha and remote_sha != local_sha),
        "fetched": fetch_ok,
        "errors": errors,
    }


@api.post("/admin/github/update")
async def github_update(admin: dict = Depends(require_admin)):
    """Pull latest from origin and (best-effort) trigger a rebuild via docker.sock."""
    settings = await get_settings()
    repo_path, path_err = _detect_repo_path()
    branch = settings.get("github_branch") or "main"
    if path_err:
        raise HTTPException(400, path_err)
    remote_url, _ = _git_or_err(repo_path, "config", "--get", "remote.origin.url")
    if not remote_url:
        raise HTTPException(
            400,
            "No git remote configured. Use the 'Configure remote' button below "
            "or run `git remote add origin <url>` in the host clone "
            "(typically /opt/streamhub) and retry.",
        )
    pull = _git(repo_path, "pull", "origin", branch)
    out = {"pull_rc": pull.returncode, "stdout": pull.stdout, "stderr": pull.stderr}
    if pull.returncode != 0:
        raise HTTPException(400, f"git pull failed: {(pull.stderr or pull.stdout).strip()}")
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


class GithubRemoteReq(BaseModel):
    url: str  # https://github.com/user/repo.git OR git@github.com:user/repo.git
    branch: str = "main"


@api.post("/admin/github/set-remote")
async def admin_github_set_remote(req: GithubRemoteReq, admin: dict = Depends(require_admin)):
    """Configure (or replace) the git remote on the host clone — no shell access required."""
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "Empty URL")
    if not (url.startswith("https://") or url.startswith("git@") or url.startswith("http://")):
        raise HTTPException(400, "URL must start with https://, http://, or git@")
    repo_path, path_err = _detect_repo_path()
    if path_err:
        raise HTTPException(400, path_err)
    existing, _ = _git_or_err(repo_path, "config", "--get", "remote.origin.url")
    if existing:
        r = _git(repo_path, "remote", "set-url", "origin", url)
    else:
        r = _git(repo_path, "remote", "add", "origin", url)
    if r.returncode != 0:
        raise HTTPException(400, f"git remote: {(r.stderr or r.stdout).strip()}")
    # Persist branch + remote-as-mirror-of-truth in settings for diagnostics
    cur = await get_settings()
    cur["github_repo"] = url
    cur["github_branch"] = req.branch or "main"
    await save_settings(cur)
    return {"ok": True, "remote_url": url, "branch": cur["github_branch"]}


@api.delete("/admin/github/remote")
async def admin_github_unset_remote(admin: dict = Depends(require_admin)):
    """Remove the git origin remote — useful when admin entered a wrong URL."""
    repo_path, path_err = _detect_repo_path()
    if path_err:
        raise HTTPException(400, path_err)
    existing, _ = _git_or_err(repo_path, "config", "--get", "remote.origin.url")
    if existing:
        _git(repo_path, "remote", "remove", "origin")
    cur = await get_settings()
    cur["github_repo"] = ""
    cur["github_token"] = ""
    await save_settings(cur)
    return {"ok": True}


class GithubTokenReq(BaseModel):
    """Friendlier form-driven remote configuration that avoids asking the admin
    to hand-craft a PAT-embedded HTTPS URL.

    Accepts either `repo_url` (e.g. https://github.com/owner/repo.git) OR the
    decomposed `owner` + `repo` fields, plus a Personal Access Token.  The PAT
    is embedded server-side into the git remote URL on disk (git config) and
    NEVER returned in API responses or stored in settings.
    """
    repo_url: Optional[str] = None
    owner: Optional[str] = None
    repo: Optional[str] = None
    username: Optional[str] = None  # optional, falls back to "x-access-token" or owner
    token: str
    branch: str = "main"


@api.post("/admin/github/set-remote-with-token")
async def admin_github_set_remote_with_token(
    req: GithubTokenReq, admin: dict = Depends(require_admin)
):
    """Configure git origin using a GitHub Personal Access Token.

    Builds `https://<user>:<token>@github.com/<owner>/<repo>.git` and writes it
    to the host clone's git config.  The token is also persisted in
    AppSettings (`github_token`) so it survives container rebuilds — the
    public-facing URL stored in `github_repo` is the SCRUBBED variant.
    """
    token = (req.token or "").strip()
    if not token:
        raise HTTPException(400, "token is required")
    # Resolve owner/repo
    owner = (req.owner or "").strip()
    repo = (req.repo or "").strip()
    if req.repo_url:
        # Accept full HTTPS or owner/repo strings
        url_in = req.repo_url.strip()
        if url_in.startswith("http://") or url_in.startswith("https://"):
            # Parse https://github.com/<owner>/<repo>(.git)
            try:
                tail = url_in.split("github.com/", 1)[1]
                parts = tail.rstrip("/").split("/")
                if len(parts) >= 2:
                    owner = owner or parts[0]
                    repo = repo or parts[1].removesuffix(".git")
            except Exception:
                raise HTTPException(400, "Could not parse repo_url; expected https://github.com/<owner>/<repo>(.git)")
        elif "/" in url_in:
            o, r = url_in.split("/", 1)
            owner = owner or o
            repo = repo or r.removesuffix(".git")
    if not owner or not repo:
        raise HTTPException(400, "Provide either repo_url or both owner+repo")
    username = (req.username or owner or "x-access-token").strip()
    branch = (req.branch or "main").strip() or "main"

    # PAT-embedded URL (lives only in git config on disk)
    auth_url = f"https://{username}:{token}@github.com/{owner}/{repo}.git"
    display_url = f"https://github.com/{owner}/{repo}.git"

    repo_path, path_err = _detect_repo_path()
    if path_err:
        raise HTTPException(400, path_err)
    existing, _ = _git_or_err(repo_path, "config", "--get", "remote.origin.url")
    if existing:
        r = _git(repo_path, "remote", "set-url", "origin", auth_url)
    else:
        r = _git(repo_path, "remote", "add", "origin", auth_url)
    if r.returncode != 0:
        # Make sure we don't echo the token back even if git embeds it in errors
        raise HTTPException(400, f"git remote: {(r.stderr or r.stdout).strip().replace(token, '***')}")
    # Verify connectivity right away so we surface auth failures while the admin
    # is still on the form — far better UX than a successful save followed by a
    # silent "Check for updates" failure.
    fetch = _git(repo_path, "fetch", "origin", branch)
    if fetch.returncode != 0:
        err = (fetch.stderr or fetch.stdout).strip().replace(token, "***")
        # Roll back so we don't leave a broken remote in git config
        if existing:
            _git(repo_path, "remote", "set-url", "origin", existing)
        else:
            _git(repo_path, "remote", "remove", "origin")
        raise HTTPException(400, f"GitHub auth/fetch failed: {err}")

    cur = await get_settings()
    cur["github_repo"] = display_url  # scrubbed — safe to show in UI
    cur["github_token"] = token  # used by future rebuilds / reset-remote-after-pull flows
    cur["github_branch"] = branch
    await save_settings(cur)
    return {"ok": True, "remote_url": display_url, "branch": branch}


# ============ STARTUP ============
@app.on_event("startup")
async def startup():
    # Wait for MongoDB to be reachable (it may still be initialising on first boot).
    # This is critical on a fresh VPS install where the backend & mongo containers
    # come up together — without it, the backend would crash and restart-loop.
    for attempt in range(30):
        try:
            await client.admin.command("ping")
            break
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[startup] Mongo not ready yet (try {attempt + 1}/30): {e}")
            await asyncio.sleep(2)
    else:
        logger.error("[startup] Mongo never became reachable — failing fast")
        raise RuntimeError("MongoDB unreachable after 60 s")
    # Ensure settings exist
    try:
        s = await get_settings()
        # Bootstrap JWT secret: prefer DB value, else generate-and-persist one. This
        # makes the deployment self-contained — `.env` only needs MONGO_URL + DB_NAME.
        db_jwt = (s.get("jwt_secret") or "").strip()
        if not db_jwt:
            db_jwt = secrets.token_urlsafe(64)
            await save_settings({**s, "jwt_secret": db_jwt})
        # Inject into auth module so create_token / decode_token use it
        set_jwt_secret(db_jwt)
        # Seed default categories if empty
        if await db.categories.count_documents({}) == 0:
            for name in ["Music", "Gaming", "Tech", "Education", "Comedy", "Travel"]:
                c = Category(name=name, slug=slugify(name))
                await db.categories.insert_one(c.model_dump())
        # Bootstrap an admin only from explicit env (ADMIN_BOOTSTRAP_EMAIL/PASSWORD),
        # never write admin password to .env. Removes the auto-fallback that used
        # to insert a hardcoded "admin@streamhub.io / Admin123!" account.
        be = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "").strip().lower()
        bp = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "")
        if be and bp:
            existing = await db.users.find_one({"email": be})
            if not existing:
                admin = User(
                    email=be, username=be.split("@")[0],
                    password_hash=hash_password(bp),
                    role="admin", email_verified=True, is_pro=True,
                )
                await db.users.insert_one(admin.model_dump())
                logger.info(f"[startup] Bootstrapped admin {be} from ADMIN_BOOTSTRAP_* env")
    except Exception as e:  # noqa: BLE001
        # Don't let a bad/missing default crash the whole app on startup.
        logger.exception(f"[startup] non-fatal: {e}")


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
    # Persist (so admin sees it in Contact Messages even if email send fails)
    await db.contact_messages.insert_one({
        "id": new_id(), "title": title, "message": message, "email": email,
        "created_at": now_iso(),
    })
    # Send via SMTP — raises with the real error, which we surface as 502 so the
    # user knows something actually went wrong (no more silent "Sent" toast).
    if not settings.get("smtp_enabled") or not settings.get("smtp_host"):
        return {"ok": True, "delivered": False,
                "note": "Message saved. SMTP is disabled, so it wasn't emailed."}
    try:
        await send_contact_message(settings, to, email, title, message)
    except Exception as e:  # noqa: BLE001
        logger.warning("contact smtp failed: %s", e)
        # We still keep the saved message; admin can read it in the panel.
        raise HTTPException(502, f"SMTP send failed: {e}") from e
    return {"ok": True, "delivered": True}


@api.get("/admin/contact-messages")
async def admin_contact_messages(admin: dict = Depends(require_admin)):
    return await db.contact_messages.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.post("/admin/smtp/test")
async def admin_smtp_test(payload: dict, admin: dict = Depends(require_admin)):
    """Send a test email so the admin can confirm SMTP works without going
    through the public Contact form.  Returns the real SMTP error on failure."""
    to = (payload.get("to") or "").strip() or admin.get("email")
    if not to:
        raise HTTPException(400, "Provide a `to` email address")
    settings = await get_settings()
    if not settings.get("smtp_host"):
        raise HTTPException(400, "SMTP host is empty — save SMTP settings first")
    try:
        await send_test_email(settings, to)
    except Exception as e:  # noqa: BLE001
        # Most common Gmail errors annotated for clarity
        msg = str(e)
        hint = ""
        if "Username and Password not accepted" in msg or "535" in msg:
            hint = (" Hint: Gmail requires a 16-char App Password (not your normal password), "
                    "generated at myaccount.google.com → Security → 2-Step Verification → App passwords.")
        elif "STARTTLS" in msg or "starttls" in msg:
            hint = " Hint: port 465 needs SMTP security = 'ssl' (implicit TLS), not STARTTLS."
        elif "connection" in msg.lower() and "refused" in msg.lower():
            hint = " Hint: check the firewall / outgoing port 587/465 from your VPS to Gmail."
        raise HTTPException(502, f"SMTP test failed: {e}.{hint}") from e
    return {"ok": True, "sent_to": to}


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
    """Public site identity / SEO + localisation + chat config consumed by the frontend."""
    s = await get_settings()
    return {
        "title": s.get("site_title") or "StreamHub",
        "description": s.get("site_description") or "",
        "favicon_url": s.get("site_favicon_url") or "",
        "logo_url": s.get("site_logo_url") or "",
        "keywords": s.get("site_seo_keywords") or "",
        "meta": s.get("site_seo_meta") or "",
        "default_language": s.get("default_language") or "ro",
        "shorts_max_duration_sec": int(s.get("shorts_max_duration_sec", 60)),
        "live_chat_enabled": bool(s.get("live_chat_enabled", True)),
        "live_chat_guest_allowed": bool(s.get("live_chat_guest_allowed", True)),
        "live_chat_max_message_length": int(s.get("live_chat_max_message_length", 500)),
    }


# ============ Admin: site logo upload ============
(UPLOAD_DIR / "branding").mkdir(exist_ok=True)


@api.post("/admin/site/logo")
async def admin_upload_logo(
    file: UploadFile = File(...), admin: dict = Depends(require_admin)
):
    """Upload the left-sidebar / brand logo image.

    Accepts any image; saved to /uploads/branding/site_logo.<ext> with a
    cache-busting suffix so the browser picks up the new file immediately.
    Falls back to local disk if Wasabi isn't configured.
    """
    ext = (Path(file.filename or "img").suffix or ".png").lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
        raise HTTPException(400, "Unsupported image format")
    import time as _t
    fname = f"site_logo_{int(_t.time())}{ext}"
    out_path = UPLOAD_DIR / "branding" / fname
    with open(out_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = f"branding/{fname}"
    settings = await get_settings()
    if wasabi_configured(settings):
        url = await wasabi_upload(str(out_path), rel, settings)
        if url:
            rel = url
            try:
                out_path.unlink()
            except Exception:
                pass
    cur = await get_settings()
    cur["site_logo_url"] = rel
    await save_settings(cur)
    return {"site_logo_url": rel}


@api.delete("/admin/site/logo")
async def admin_delete_logo(admin: dict = Depends(require_admin)):
    """Reset to the default 'S' + StreamHub text mark."""
    cur = await get_settings()
    cur["site_logo_url"] = ""
    await save_settings(cur)
    return {"ok": True}


# ============ LIVE CHAT ============
_chat_last_send: dict[str, float] = {}


def _chat_is_banned(user: Optional[dict], guest_session: Optional[str], guest_bans: list[dict]) -> Optional[str]:
    """Return reason string if banned, else None."""
    now = datetime.now(timezone.utc)
    if user:
        cbu = user.get("chat_banned_until")
        if cbu == "permanent":
            return user.get("chat_banned_reason") or "Permanently banned from chat"
        if cbu:
            try:
                if datetime.fromisoformat(cbu) > now:
                    return user.get("chat_banned_reason") or f"Chat-banned until {cbu}"
            except ValueError:
                pass
    if guest_session:
        for b in guest_bans:
            if b.get("guest_session") != guest_session:
                continue
            bu = b.get("banned_until")
            if bu == "permanent":
                return b.get("reason") or "Permanently banned from chat"
            try:
                if datetime.fromisoformat(bu) > now:
                    return b.get("reason") or f"Chat-banned until {bu}"
            except ValueError:
                pass
    return None


@api.get("/chat/messages")
async def chat_messages(limit: int = 50):
    cur = db.chat_messages.find({}, {"_id": 0}).sort("created_at", -1).limit(min(limit, 200))
    msgs = await cur.to_list(limit)
    return list(reversed(msgs))  # oldest first for UI


@api.post("/chat/send")
async def chat_send(req: ChatSendReq, user: Optional[dict] = Depends(current_user)):
    settings = await get_settings()
    if not settings.get("live_chat_enabled", True):
        raise HTTPException(503, "Chat disabled")
    content = (req.content or "").strip()
    if not content:
        raise HTTPException(400, "Empty message")
    max_len = int(settings.get("live_chat_max_message_length", 500))
    if len(content) > max_len:
        raise HTTPException(400, f"Message exceeds {max_len} characters")

    guest_session = None
    guest_name = None
    if not user:
        if not settings.get("live_chat_guest_allowed", True):
            raise HTTPException(401, "Guest chat not allowed")
        guest_session = (req.guest_session or "").strip()
        guest_name = (req.guest_name or "").strip()
        if not guest_session or not guest_name:
            raise HTTPException(400, "Guest must provide session id and name")
        if len(guest_name) > 30:
            raise HTTPException(400, "Guest name too long")

    # Rate-limit: one message per window seconds per principal
    rate_key = user["id"] if user else f"guest:{guest_session}"
    rate_window = int(settings.get("live_chat_rate_limit_seconds", 3))
    now = time.time()
    last = _chat_last_send.get(rate_key, 0)
    if now - last < rate_window:
        raise HTTPException(429, f"Slow down — wait {rate_window - int(now - last)}s")
    # Ban check
    guest_bans = await db.chat_bans.find({}, {"_id": 0}).to_list(1000)
    reason = _chat_is_banned(user, guest_session, guest_bans)
    if reason:
        raise HTTPException(403, reason)

    msg = ChatMessage(
        user_id=user["id"] if user else None,
        guest_session=guest_session,
        username=user["username"] if user else guest_name,
        avatar_url=user.get("avatar_url") if user else None,
        is_pro=bool(user.get("is_pro")) if user else False,
        role=("admin" if user and user.get("role") == "admin" else ("user" if user else "guest")),
        content=content,
    )
    await db.chat_messages.insert_one(msg.model_dump())
    _chat_last_send[rate_key] = now
    # Trim to last 500
    total = await db.chat_messages.count_documents({})
    if total > 500:
        # Delete oldest
        oldest = await db.chat_messages.find({}, {"_id": 0, "id": 1, "created_at": 1}).sort("created_at", 1).limit(total - 500).to_list(total)
        ids = [x["id"] for x in oldest]
        if ids:
            await db.chat_messages.delete_many({"id": {"$in": ids}})
    await chat_hub.broadcast({"type": "message", "data": msg.model_dump()})
    return msg.model_dump()


@api.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket):
    cid = await chat_hub.connect(websocket)
    try:
        while True:
            # Keep-alive: clients aren't expected to send (they POST /chat/send),
            # but we must read to detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.debug("chat ws closed: %s", e)
    finally:
        await chat_hub.disconnect(cid)


@api.websocket("/videos/{video_id}/status")
async def video_status_ws(websocket: WebSocket, video_id: str):
    """Push live progress / status updates for one video while it's transcoding.

    The client receives an immediate snapshot on connect, then incremental
    `{type: 'video.status', video_id, data}` packets whenever process_video
    flips its progress.  Replaces the older HTTP polling loop on the watch page.
    """
    cid = await video_status_hub.connect(video_id, websocket)
    try:
        # Send an initial snapshot so the UI doesn't need a separate fetch.
        snap = await db.videos.find_one(
            {"id": video_id},
            {"_id": 0, "status": 1, "progress": 1, "renditions": 1, "error": 1,
             "thumbnail_url": 1, "is_short": 1, "duration_sec": 1},
        )
        if snap:
            import json as _json
            await websocket.send_text(_json.dumps(
                {"type": "video.status", "video_id": video_id, "data": snap}, default=str,
            ))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.debug("video.status ws closed: %s", e)
    finally:
        await video_status_hub.disconnect(video_id, cid)


def _ban_until_from_req(req: ChatBanReq) -> str:
    now = datetime.now(timezone.utc)
    if req.duration == "permanent":
        return "permanent"
    if req.duration == "1day":
        return (now + timedelta(days=1)).isoformat()
    if req.duration == "1week":
        return (now + timedelta(days=7)).isoformat()
    if req.duration == "1month":
        return (now + timedelta(days=30)).isoformat()
    if req.duration == "custom":
        return (now + timedelta(days=int(req.custom_days or 1))).isoformat()
    raise HTTPException(400, "Invalid duration")


@api.post("/admin/chat/ban-user/{user_id}")
async def admin_chat_ban_user(user_id: str, req: ChatBanReq, admin: dict = Depends(require_admin)):
    until = _ban_until_from_req(req)
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"chat_banned_until": until, "chat_banned_reason": req.reason or ""}},
    )
    return {"ok": True, "chat_banned_until": until}


@api.post("/admin/chat/unban-user/{user_id}")
async def admin_chat_unban_user(user_id: str, admin: dict = Depends(require_admin)):
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"chat_banned_until": None, "chat_banned_reason": None}},
    )
    return {"ok": True}


@api.post("/admin/chat/ban-guest/{guest_session}")
async def admin_chat_ban_guest(guest_session: str, req: ChatBanReq, admin: dict = Depends(require_admin)):
    until = _ban_until_from_req(req)
    await db.chat_bans.update_one(
        {"guest_session": guest_session},
        {"$set": GuestChatBan(guest_session=guest_session, banned_until=until, reason=req.reason).model_dump()},
        upsert=True,
    )
    return {"ok": True, "banned_until": until}


@api.post("/admin/chat/unban-guest/{guest_session}")
async def admin_chat_unban_guest(guest_session: str, admin: dict = Depends(require_admin)):
    await db.chat_bans.delete_one({"guest_session": guest_session})
    return {"ok": True}


@api.delete("/admin/chat/messages/{msg_id}")
async def admin_delete_chat_message(msg_id: str, admin: dict = Depends(require_admin)):
    await db.chat_messages.delete_one({"id": msg_id})
    await chat_hub.broadcast({"type": "delete", "data": {"id": msg_id}})
    return {"ok": True}


@api.get("/admin/chat/bans")
async def admin_chat_bans(admin: dict = Depends(require_admin)):
    users = await db.users.find(
        {"chat_banned_until": {"$ne": None}},
        {"_id": 0, "id": 1, "username": 1, "email": 1, "chat_banned_until": 1, "chat_banned_reason": 1},
    ).to_list(500)
    guests = await db.chat_bans.find({}, {"_id": 0}).to_list(500)
    return {"users": users, "guests": guests}


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
