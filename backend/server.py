"""StreamHub backend - FastAPI app."""
import asyncio
import json
import logging
import os
import random
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

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
    AvatarFrame,
    BanReq,
    Category,
    ChatBanReq,
    ChatMessage,
    ChatSendReq,
    CoinTxn,
    Comment,
    CommentReq,
    GuestChatBan,
    LoginReq,
    Package,
    PaymentTransaction,
    RegisterReq,
    ShortsSeries,
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
    extract_embedded_subtitles,
    filter_resolutions_for_source,
    generate_thumbnails,
    probe_video,
    transcode_to_resolution,
)
from languages import (
    LANGUAGES,
    LABEL_BY_CODE as LANG_LABEL_BY_CODE,
    detect_language_from_filename,
    normalize_language_code,
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


def public_user(u: dict, include_email: bool = False) -> dict:
    if not u:
        return None
    data = UserPublic(**u).model_dump()
    if include_email:
        data["email"] = u.get("email")
    else:
        # Strip email entirely so it never leaks in public profile responses.
        data.pop("email", None)
    return data


async def public_user_with_frame(u: dict, include_email: bool = False) -> dict:
    """Same as `public_user` but additionally attaches the user's selected
    avatar-frame doc (if any) so the client doesn't need a second fetch."""
    data = public_user(u, include_email=include_email)
    if data and u.get("selected_frame_id"):
        frame = await db.avatar_frames.find_one({"id": u["selected_frame_id"]}, {"_id": 0})
        data["selected_frame"] = frame
    else:
        data["selected_frame"] = None
    return data


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


async def build_video_slug(title: str, video_id: str) -> str:
    """Return `<slug>-<short>` where short = last 6 chars of the UUID.

    The slug uses the FULL title (slugified) — no length cap, so long titles
    fit into the URL completely.  Browsers handle multi-hundred-char URLs
    fine and search engines reward keyword-rich slugs.

    Guaranteed unique because the trailing 6-char UUID hex segment makes
    collisions astronomically rare.
    """
    base = slugify(title).strip("-") or "video"
    short = (video_id or new_id()).replace("-", "")[-6:]
    return f"{base}-{short}"


async def find_video_by_id_or_slug(key: str) -> Optional[dict]:
    """Resolve `key` against either `id` (UUID) or `slug` (SEO URL).

    Lookup strategy (in order):
      1. Exact match on `id` (canonical UUID).
      2. Exact match on `slug` (current SEO URL).
      3. Exact match on `legacy_slug` (the slug before the last
         backfill — preserves links shared before this release).
      4. **UUID-suffix fallback**: every slug generated by
         :func:`build_video_slug` ends in `-<6 hex chars>` where those 6
         chars are the *tail* of the canonical UUID (after stripping
         dashes).  When the slug body doesn't match anymore (e.g. the
         admin renamed the video), we can still find it by isolating
         that suffix and querying for `id` ending with it.
      5. **Legacy `_<rand>.html` suffix**: the previous CMS format —
         e.g. ``kutsujoku-sezonul-2-episodul-1-rosub_ksZSCSL44VkOuF6.html``.
         We look up by `legacy_slug` regex when the key ends in `.html`.
      6. Prefix lookup on `slug` — handles old shared links that used a
         truncated version of the slug from before this release.

    Post-processing: `synopsis` field is normalized to `""` for legacy
    docs that predate the AI Synopsis feature so callers never have to
    check for its presence.
    """
    def _normalize(doc):
        if doc is not None and "synopsis" not in doc:
            doc["synopsis"] = ""
        return doc

    if not key:
        return None
    v = await db.videos.find_one({"id": key}, {"_id": 0})
    if v:
        return _normalize(v)
    v = await db.videos.find_one({"slug": key}, {"_id": 0})
    if v:
        return _normalize(v)
    v = await db.videos.find_one({"legacy_slug": key}, {"_id": 0})
    if v:
        return _normalize(v)

    # ---- UUID-suffix fallback (the most robust path) -------------------
    m = re.search(r"-([0-9a-fA-F]{6})$", key)
    if m:
        suffix = m.group(1).lower()
        # `id` has dashes — match against UUIDs whose hex tail (after
        # removing the last dash) ends with `suffix`.
        # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx → final 12 hex.
        v = await db.videos.find_one(
            {"id": {"$regex": f"{suffix}$", "$options": "i"}},
            {"_id": 0},
        )
        if v:
            return _normalize(v)

    # ---- Legacy `_<rand>.html` URLs ------------------------------------
    if key.endswith(".html"):
        v = await db.videos.find_one(
            {"$or": [
                {"legacy_slug": {"$regex": f"{re.escape(key)}$"}},
                {"legacy_slug": key[:-5]},  # strip the trailing .html
            ]},
            {"_id": 0},
        )
        if v:
            return _normalize(v)

    # ---- Slug-prefix fallback ------------------------------------------
    if len(key) > 10:
        v = await db.videos.find_one(
            {"slug": {"$regex": f"^{re.escape(key)}"}}, {"_id": 0},
        )
        if v:
            return _normalize(v)
    return None


async def resolve_video_id(key: str) -> Optional[str]:
    """Resolve `key` (slug OR uuid) → the canonical Video.id, or None."""
    v = await find_video_by_id_or_slug(key)
    return v["id"] if v else None


@api.get("/admin/og-debug/{key:path}")
async def og_debug(key: str, request: Request, admin: dict = Depends(require_admin)):
    """Admin-only diagnostic: shows EXACTLY what the OG endpoint would render
    for `key` (slug, uuid, legacy_slug, or arbitrary string).  Lets the admin
    test link previews on the VPS without using the Facebook debugger.
    """
    v = await find_video_by_id_or_slug(key)
    s = await get_settings()
    base = (s.get("site_canonical_url") or "").rstrip("/")
    if not base:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        host = request.headers.get("host") or request.url.hostname or ""
        base = f"{proto}://{host}" if host else ""
    return {
        "input_key": key,
        "video_found": bool(v),
        "matched_video": (
            None if not v else {
                "id": v.get("id"),
                "title": v.get("title"),
                "slug": v.get("slug"),
                "legacy_slug": v.get("legacy_slug"),
                "thumbnail_url": v.get("thumbnail_url"),
                "thumbnail_url_absolute": _absolute_og_image(
                    v.get("thumbnail_url") or "", base,
                ) if v.get("thumbnail_url") else None,
            }
        ),
        "computed_og": {
            "title": (f"{v.get('title')} — {s.get('site_title') or 'StreamHub'}" if v else (s.get("site_title") or "StreamHub")),
            "description": (
                (v.get("description") or "").strip()[:200] if v
                else (s.get("site_description") or "")
            ),
            "og_image": _absolute_og_image(
                (v.get("thumbnail_url") if v else "") or s.get("site_og_image") or "",
                base,
            ),
            "page_url": f"{base}/watch/{key}" if base else f"/watch/{key}",
        },
        "site_config_canonical_url": s.get("site_canonical_url"),
        "request_host": request.headers.get("host"),
        "request_scheme": request.headers.get("x-forwarded-proto") or request.url.scheme,
        "videos_total_in_db": await db.videos.count_documents({}),
        "videos_with_slug": await db.videos.count_documents({"slug": {"$exists": True, "$nin": [None, ""]}}),
    }


# ============ Coin economy helpers ============
async def _award_coins(user_id: str, delta: int, reason: str) -> int:
    """Atomically credit (delta>0) or debit (delta<0) coins to a user and
    record an entry in the `coin_ledger` collection.  Returns the new balance.
    The ledger entry is used for idempotency (e.g. one like per video).
    """
    res = await db.users.find_one_and_update(
        {"id": user_id},
        {"$inc": {"coins": int(delta)}},
        return_document=True,
        projection={"_id": 0, "coins": 1},
    )
    new_balance = int((res or {}).get("coins", 0))
    await db.coin_ledger.insert_one({
        "id": new_id(),
        "user_id": user_id,
        "delta": int(delta),
        "reason": reason,
        "balance_after": new_balance,
        "created_at": now_iso(),
    })
    return new_balance


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
            # Generate 20 thumbnails (per admin request — was 10)
            thumb_dir = UPLOAD_DIR / "thumbnails"
            thumbs = await generate_thumbnails(
                src_path, str(thumb_dir), video_id, duration, 20
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
            # ----- Auto-extract embedded text subtitles (MKV / MP4 / MOV) ----
            try:
                sub_dir = UPLOAD_DIR / "subtitles"
                sub_dir.mkdir(parents=True, exist_ok=True)
                extracted = await extract_embedded_subtitles(src_path, str(sub_dir), video_id)
                if extracted:
                    new_subs: List[dict] = []
                    for item in extracted:
                        local_path = Path(item["rel_path"])
                        rel = f"subtitles/{local_path.name}"
                        final_url = rel
                        if use_wasabi:
                            uploaded = await wasabi_upload(
                                str(local_path), rel, settings, "text/vtt; charset=utf-8",
                            )
                            if uploaded:
                                final_url = uploaded
                                try:
                                    local_path.unlink()
                                except Exception:
                                    pass
                        new_subs.append({
                            "id": new_id(),
                            "language": normalize_language_code(item.get("language") or "") or "und",
                            "label": item.get("label") or "Track",
                            "url": final_url,
                            "original_url": "",
                            "source": "embedded",  # mark for the UI
                        })
                    if new_subs:
                        await db.videos.update_one(
                            {"id": video_id},
                            {"$push": {"subtitles": {"$each": new_subs}}},
                        )
                        logger.info(
                            "Extracted %d embedded subtitle(s) from %s",
                            len(new_subs), Path(src_path).name,
                        )
            except Exception as _sub_err:  # noqa: BLE001
                # Subtitle extraction must NEVER break a video upload.
                logger.warning("subtitle extraction failed: %s", _sub_err)
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
    return {"token": token, "user": await public_user_with_frame(u.model_dump(), include_email=True)}


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
    # Check vip expiry
    if u.get("is_vip") and u.get("vip_expires_at"):
        try:
            if datetime.fromisoformat(u["vip_expires_at"]) < datetime.now(timezone.utc):
                await db.users.update_one({"id": u["id"]}, {"$set": {"is_vip": False}})
                u["is_vip"] = False
        except ValueError:
            pass
    token = create_token(u["id"])
    _rate_limit_reset(rate_key)
    return {"token": token, "user": await public_user_with_frame(u, include_email=True)}


@api.get("/auth/me")
async def me(user: dict = Depends(require_user)):
    return await public_user_with_frame(user, include_email=True)


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
async def get_user(user_id: str, viewer: Optional[dict] = Depends(current_user)):
    u = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Not found")
    # Only the owner / admin can see the email
    include_email = bool(viewer and (viewer.get("id") == u.get("id") or viewer.get("role") == "admin"))
    return await public_user_with_frame(u, include_email=include_email)


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
    return await public_user_with_frame(u, include_email=True)


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
    name_en = (payload.get("name_en") or "").strip()
    slug = slugify(name)
    if await db.categories.find_one({"slug": slug}):
        raise HTTPException(400, "Category exists")
    c = Category(name=name, name_en=name_en, slug=slug)
    await db.categories.insert_one(c.model_dump())
    return c.model_dump()


@api.patch("/categories/{cat_id}")
async def update_category(cat_id: str, payload: dict, admin: dict = Depends(require_admin)):
    upd = {}
    if "name" in payload:
        upd["name"] = (payload.get("name") or "").strip()
    if "name_en" in payload:
        upd["name_en"] = (payload.get("name_en") or "").strip()
    if not upd:
        return {"ok": True}
    await db.categories.update_one({"id": cat_id}, {"$set": upd})
    return {"ok": True}


@api.delete("/categories/{cat_id}")
async def delete_category(cat_id: str, admin: dict = Depends(require_admin)):
    await db.categories.delete_one({"id": cat_id})
    return {"ok": True}


# ============ SHORTS SERIES ============
async def _series_with_stats(s: dict) -> dict:
    """Attach episode_count so the frontend can render Netflix-style poster cards."""
    if not s:
        return s
    s.pop("_id", None)
    s["episode_count"] = await db.videos.count_documents({
        "shorts_series_id": s["id"],
        "status": "ready",
    })
    return s


@api.get("/shorts-series")
async def list_shorts_series():
    """Public — active series only, sorted by sort_order then name."""
    docs = await db.shorts_series.find({"active": True}, {"_id": 0}) \
        .sort([("sort_order", 1), ("name", 1)]).to_list(200)
    for d in docs:
        d["episode_count"] = await db.videos.count_documents({
            "shorts_series_id": d["id"], "status": "ready",
        })
    return docs


@api.get("/shorts-series/all")
async def list_all_shorts_series(admin: dict = Depends(require_admin)):
    """Admin — everything, active or not."""
    docs = await db.shorts_series.find({}, {"_id": 0}) \
        .sort([("sort_order", 1), ("name", 1)]).to_list(500)
    for d in docs:
        d["episode_count"] = await db.videos.count_documents({"shorts_series_id": d["id"]})
    return docs


@api.get("/shorts-series/{key}")
async def get_shorts_series(key: str):
    s = await db.shorts_series.find_one({"$or": [{"id": key}, {"slug": key}]}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Series not found")
    # Return series + episodes ordered by shorts_series_position (nulls last), then created_at asc
    episodes = await db.videos.find(
        {"shorts_series_id": s["id"], "status": "ready"},
        {"_id": 0},
    ).to_list(500)
    episodes.sort(key=lambda v: (
        v.get("shorts_series_position") if v.get("shorts_series_position") is not None else 10 ** 9,
        v.get("created_at") or "",
    ))
    s["episodes"] = episodes
    s["episode_count"] = len(episodes)
    return s


@api.post("/shorts-series")
async def create_shorts_series(payload: dict, admin: dict = Depends(require_admin)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    slug = (payload.get("slug") or slugify(name)).strip() or slugify(name)
    if await db.shorts_series.find_one({"slug": slug}):
        raise HTTPException(400, "A series with this slug already exists")
    s = ShortsSeries(
        name=name,
        slug=slug,
        description=(payload.get("description") or "").strip(),
        cover_thumbnail=(payload.get("cover_thumbnail") or "").strip(),
        tags=[t.strip() for t in (payload.get("tags") or []) if str(t).strip()],
        active=bool(payload.get("active", True)),
        sort_order=int(payload.get("sort_order") or 0),
    )
    await db.shorts_series.insert_one(s.model_dump())
    return s.model_dump()


@api.patch("/shorts-series/{series_id}")
async def update_shorts_series(series_id: str, payload: dict, admin: dict = Depends(require_admin)):
    allowed = {"name", "slug", "description", "cover_thumbnail", "tags", "active", "sort_order"}
    upd = {k: v for k, v in payload.items() if k in allowed}
    if not upd:
        return {"ok": True}
    # If slug changed, ensure uniqueness
    if "slug" in upd:
        upd["slug"] = (upd["slug"] or "").strip()
        clash = await db.shorts_series.find_one({"slug": upd["slug"], "id": {"$ne": series_id}})
        if clash:
            raise HTTPException(400, "Another series already uses this slug")
    await db.shorts_series.update_one({"id": series_id}, {"$set": upd})
    s = await db.shorts_series.find_one({"id": series_id}, {"_id": 0})
    return await _series_with_stats(s)


@api.delete("/shorts-series/{series_id}")
async def delete_shorts_series(series_id: str, admin: dict = Depends(require_admin)):
    # Unassign videos then remove the series document
    await db.videos.update_many(
        {"shorts_series_id": series_id},
        {"$set": {"shorts_series_id": None, "shorts_series_position": None}},
    )
    await db.shorts_series.delete_one({"id": series_id})
    return {"ok": True}


@api.post("/shorts-series/{series_id}/cover")
async def upload_shorts_series_cover(
    series_id: str,
    file: UploadFile = File(...),
    admin: dict = Depends(require_admin),
):
    """Upload a portrait cover thumbnail for a series. Stored in Wasabi when configured."""
    series = await db.shorts_series.find_one({"id": series_id}, {"_id": 0})
    if not series:
        raise HTTPException(404, "Series not found")
    ext = (Path(file.filename or "img").suffix or ".jpg").lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise HTTPException(400, "Only jpg/png/webp/gif images are allowed")
    fname = f"{series_id}_cover{ext}"
    out_path = UPLOAD_DIR / "series_covers" / fname
    out_path.parent.mkdir(exist_ok=True, parents=True)
    with open(out_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = f"series_covers/{fname}"
    settings = await get_settings()
    if wasabi_configured(settings):
        content_type = f"image/{ext.lstrip('.').replace('jpg', 'jpeg')}"
        url = await wasabi_upload(str(out_path), rel, settings, content_type)
        if url:
            rel = url
            try:
                out_path.unlink()
            except Exception:
                pass
    await db.shorts_series.update_one({"id": series_id}, {"$set": {"cover_thumbnail": rel}})
    return {"cover_thumbnail": rel}


@api.post("/shorts-series/{series_id}/reorder")
async def reorder_shorts_series(series_id: str, payload: dict, admin: dict = Depends(require_admin)):
    """Body: {video_ids: [...]}. Positions are 1-indexed in the order supplied."""
    ids = payload.get("video_ids") or []
    if not isinstance(ids, list):
        raise HTTPException(400, "video_ids must be a list")
    for pos, vid in enumerate(ids, start=1):
        await db.videos.update_one(
            {"id": vid, "shorts_series_id": series_id},
            {"$set": {"shorts_series_position": pos}},
        )
    return {"ok": True, "count": len(ids)}


# ============ VIDEOS ============
@api.get("/videos")
async def list_videos(
    section: str = "latest",
    category_id: Optional[str] = None,
    category_ids: Optional[str] = None,  # comma-separated; up to 2 — extra are ignored
    kind: Optional[str] = None,  # "video" (long) | "short" | None (all)
    access_tier: Optional[str] = None,  # "free" | "pro" | None (both)
    shorts_series_id: Optional[str] = None,
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
    if access_tier in ("free", "pro", "vip"):
        filt["access_tier"] = access_tier
    if shorts_series_id:
        filt["shorts_series_id"] = shorts_series_id
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
        items = await cur.to_list(limit)
    elif section == "random":
        pipeline = [{"$match": filt}, {"$sample": {"size": limit + skip}},
                    {"$project": {"_id": 0}}, {"$skip": skip}, {"$limit": limit}]
        items = await db.videos.aggregate(pipeline).to_list(limit)
    else:
        cur = db.videos.find(filt, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        items = await cur.to_list(limit)
    # Decorate each video with comments_count for the cards (cheap fan-out).
    if items:
        ids = [v["id"] for v in items]
        pipeline = [
            {"$match": {"video_id": {"$in": ids}}},
            {"$group": {"_id": "$video_id", "n": {"$sum": 1}}},
        ]
        counts = {r["_id"]: r["n"] async for r in db.comments.aggregate(pipeline)}
        for v in items:
            v["comments_count"] = counts.get(v["id"], 0)
    return items


@api.get("/videos/count")
async def count_videos(
    section: str = "latest",  # noqa: ARG001 — kept for API compat; ordering doesn't change count
    category_id: Optional[str] = None,
    category_ids: Optional[str] = None,
    kind: Optional[str] = None,
    access_tier: Optional[str] = None,
    shorts_series_id: Optional[str] = None,
    q: Optional[str] = None,
):
    """Counts videos matching the same filters list_videos accepts.

    Used by the frontend numbered pagination to compute the total page count.
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
    if access_tier in ("free", "pro", "vip"):
        filt["access_tier"] = access_tier
    if shorts_series_id:
        filt["shorts_series_id"] = shorts_series_id
    if q:
        import re as _re
        rex = _re.escape(q.strip())
        if rex:
            filt["$or"] = [
                {"title": {"$regex": rex, "$options": "i"}},
                {"tags": {"$regex": rex, "$options": "i"}},
            ]
    return {"count": await db.videos.count_documents(filt)}


@api.get("/videos/{video_id}")
async def get_video(video_id: str, request: Request, user: Optional[dict] = Depends(current_user)):
    v = await find_video_by_id_or_slug(video_id)
    if not v:
        raise HTTPException(404, "Not found")
    tier = v.get("access_tier") or "free"
    # Access hierarchy:
    #   free -> everyone
    #   pro  -> PRO or VIP users
    #   vip  -> only VIP users
    #   admin bypass -> admins can always see the raw content (needed for the
    #                   edit page, subtitle management, thumbnail picking, etc.)
    is_admin = bool(user and user.get("role") == "admin")
    if tier in ("pro", "vip") and not is_admin:
        is_pro = bool(user and user.get("is_pro"))
        is_vip = bool(user and user.get("is_vip"))
        allowed = is_vip if tier == "vip" else (is_pro or is_vip)
        if not allowed:
            v["locked"] = True
            v["renditions"] = []
            v["subtitles"] = []
            return v
    # Sign renditions + subtitles for the response (needed for tiered content
    # AND for admins previewing paywalled videos in the edit page).
    if tier in ("pro", "vip"):
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
    vid = await resolve_video_id(video_id)
    if not vid:
        raise HTTPException(404, "Not found")
    await db.videos.update_one({"id": vid}, {"$inc": {"views": 1}})
    return {"ok": True}


@api.post("/videos/{video_id}/like")
async def toggle_like(video_id: str, user: dict = Depends(require_user)):
    v = await find_video_by_id_or_slug(video_id)
    if not v:
        raise HTTPException(404, "Not found")
    vid = v["id"]
    likes = v.get("likes", [])
    coins_awarded = 0
    if user["id"] in likes:
        likes.remove(user["id"])
        liked = False
    else:
        likes.append(user["id"])
        liked = True
        # Award coins ONLY the first time this user likes this video — prevents
        # like/unlike farming.  We use the `coin_ledger` to record idempotency.
        reason = f"like:{vid}"
        existing = await db.coin_ledger.find_one({"user_id": user["id"], "reason": reason})
        if not existing:
            settings = await get_settings()
            amt = int(settings.get("coins_per_like", 1) or 0)
            if amt > 0:
                coins_awarded = amt
                await _award_coins(user["id"], amt, reason)
    await db.videos.update_one({"id": vid}, {"$set": {"likes": likes}})
    return {"liked": liked, "count": len(likes), "coins_awarded": coins_awarded}


@api.get("/videos/{video_id}/recommendations")
async def recommendations(video_id: str, limit: int = 15):
    v = await find_video_by_id_or_slug(video_id)
    vid = v["id"] if v else video_id
    q = {"status": "ready", "id": {"$ne": vid}}
    if v and v.get("category_id"):
        # try same category first
        same = await db.videos.find(
            {**q, "category_id": v["category_id"]}, {"_id": 0}
        ).limit(limit).to_list(limit)
        if len(same) >= limit:
            return same
        # backfill with random others
        need = limit - len(same)
        exclude_ids = [vid] + [x["id"] for x in same]
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
    if access_tier not in ("free", "pro", "vip"):
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
    v_dict = v.model_dump()
    v_dict["slug"] = await build_video_slug(title, vid_id)
    await db.videos.insert_one(v_dict)
    # `insert_one` mutates `v_dict` by adding the ObjectId `_id` — strip it.
    v_dict.pop("_id", None)
    # Schedule background
    background.add_task(process_video, vid_id, str(src_path))
    return v_dict


# ============ Chunked / Resumable Video Upload ============
# Big files (≥4 GB) blow through nginx body limits and any single-shot
# multipart POST loses progress on flaky connections.  We expose 4 endpoints:
#   POST   /videos/upload/init          → declare {filename, total_size, …}
#   POST   /videos/upload/{uid}/chunk   → append the next chunk (binary)
#   GET    /videos/upload/{uid}/status  → resume info (received_size, next_idx)
#   POST   /videos/upload/{uid}/finish  → finalise and start transcoding
# Pending uploads live under UPLOAD_DIR/.chunks/<uid>/ with a `state.json` next
# to the partial `blob` so the server can recover after a restart.

CHUNKS_DIR = UPLOAD_DIR / ".chunks"
CHUNKS_DIR.mkdir(exist_ok=True, parents=True)


def _chunk_state_path(upload_id: str) -> Path:
    return CHUNKS_DIR / upload_id / "state.json"


def _chunk_blob_path(upload_id: str) -> Path:
    return CHUNKS_DIR / upload_id / "blob"


def _read_chunk_state(upload_id: str) -> Optional[dict]:
    p = _chunk_state_path(upload_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _write_chunk_state(upload_id: str, state: dict) -> None:
    p = _chunk_state_path(upload_id)
    p.parent.mkdir(exist_ok=True, parents=True)
    p.write_text(json.dumps(state))


def _purge_chunk_upload(upload_id: str) -> None:
    d = CHUNKS_DIR / upload_id
    try:
        if d.exists():
            import shutil as _sh
            _sh.rmtree(d, ignore_errors=True)
    except Exception:
        pass


def _scan_chunk_uploads() -> List[Dict]:
    """Return a metadata snapshot of every pending upload under CHUNKS_DIR."""
    out: List[Dict] = []
    if not CHUNKS_DIR.exists():
        return out
    now_ts = time.time()
    for child in CHUNKS_DIR.iterdir():
        if not child.is_dir():
            continue
        try:
            state = _read_chunk_state(child.name) or {}
            blob = child / "blob"
            size = blob.stat().st_size if blob.exists() else 0
            mtime = child.stat().st_mtime
            out.append({
                "upload_id": child.name,
                "user_id": state.get("user_id"),
                "filename": state.get("filename") or "?",
                "total_size": int(state.get("total_size", 0) or 0),
                "received_size": size,
                "created_at": state.get("created_at"),
                "age_hours": round((now_ts - mtime) / 3600.0, 2),
                "stale": (now_ts - mtime) >= 86400,  # ≥24h with no activity
            })
        except Exception:
            continue
    return out


def _cleanup_stale_chunks(max_age_hours: float = 24.0) -> int:
    """Remove every chunk directory untouched for `max_age_hours`.  Returns
    the number of pending uploads purged.
    """
    if not CHUNKS_DIR.exists():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    purged = 0
    for child in list(CHUNKS_DIR.iterdir()):
        try:
            if not child.is_dir():
                continue
            if child.stat().st_mtime < cutoff:
                _purge_chunk_upload(child.name)
                purged += 1
        except Exception:
            continue
    if purged:
        logger.info("Janitor: purged %d stale chunked upload(s)", purged)
    return purged


@api.post("/videos/upload/init")
async def upload_video_init(payload: dict, user: dict = Depends(require_user)):
    """Open a new resumable upload slot.  Returns `upload_id` + `chunk_size_mb`."""
    settings = await get_settings()
    if not settings.get("allow_user_uploads", True) and user.get("role") != "admin":
        raise HTTPException(403, "User uploads disabled by admin")
    filename = (payload.get("filename") or "").strip() or "video.mp4"
    total_size = int(payload.get("total_size") or 0)
    if total_size <= 0:
        raise HTTPException(400, "total_size required")
    max_bytes = int(settings.get("max_upload_size_mb", 1024)) * 1024 * 1024
    if total_size > max_bytes:
        raise HTTPException(413, f"File exceeds {settings.get('max_upload_size_mb')} MB limit")
    upload_id = new_id()
    state = {
        "upload_id": upload_id,
        "user_id": user["id"],
        "filename": filename,
        "total_size": total_size,
        "received_size": 0,
        "mime_type": payload.get("mime_type") or "",
        "created_at": now_iso(),
    }
    _write_chunk_state(upload_id, state)
    # Touch the blob so `os.path.getsize` always works
    _chunk_blob_path(upload_id).touch()
    return {
        "upload_id": upload_id,
        "chunk_size_mb": int(settings.get("chunk_upload_chunk_size_mb", 25)),
        "max_upload_size_mb": int(settings.get("max_upload_size_mb", 1024)),
        "received_size": 0,
    }


@api.get("/videos/upload/{upload_id}/status")
async def upload_video_status(upload_id: str, user: dict = Depends(require_user)):
    state = _read_chunk_state(upload_id)
    if not state or state.get("user_id") != user["id"]:
        raise HTTPException(404, "Unknown upload")
    blob = _chunk_blob_path(upload_id)
    received = blob.stat().st_size if blob.exists() else 0
    state["received_size"] = received
    _write_chunk_state(upload_id, state)
    return {
        "upload_id": upload_id,
        "filename": state.get("filename"),
        "total_size": state.get("total_size"),
        "received_size": received,
        "complete": received >= int(state.get("total_size") or 0),
    }


@api.post("/videos/upload/{upload_id}/chunk")
async def upload_video_chunk(
    upload_id: str,
    request: Request,
    user: dict = Depends(require_user),
):
    """Append the next chunk (raw octet-stream body) to the upload's blob.

    Client must send chunks in order.  If a chunk is lost, the client should
    call `/status` and re-send from `received_size`.  This avoids the overhead
    of per-chunk JSON envelopes for multi-GB files.
    """
    state = _read_chunk_state(upload_id)
    if not state or state.get("user_id") != user["id"]:
        raise HTTPException(404, "Unknown upload")
    total = int(state.get("total_size") or 0)
    blob = _chunk_blob_path(upload_id)
    current = blob.stat().st_size if blob.exists() else 0
    if current >= total:
        return {"received_size": current, "complete": True}
    # Stream the request body directly to disk — never buffer in RAM.
    # FastAPI/Starlette gives us the raw stream via request.stream().
    written = 0
    settings = await get_settings()
    max_bytes = int(settings.get("max_upload_size_mb", 1024)) * 1024 * 1024
    with open(blob, "ab") as f:
        async for chunk in request.stream():
            if not chunk:
                continue
            f.write(chunk)
            written += len(chunk)
            if current + written > max_bytes:
                # Abort: clean up and reject
                f.close()
                _purge_chunk_upload(upload_id)
                raise HTTPException(413, f"File exceeds {settings.get('max_upload_size_mb')} MB limit")
    new_size = current + written
    state["received_size"] = new_size
    _write_chunk_state(upload_id, state)
    return {
        "received_size": new_size,
        "total_size": total,
        "complete": new_size >= total,
    }


@api.post("/videos/upload/{upload_id}/finish")
async def upload_video_finish(
    upload_id: str,
    payload: dict,
    background: BackgroundTasks,
    user: dict = Depends(require_user),
):
    """Promote the assembled blob to a real Video doc and start transcoding."""
    state = _read_chunk_state(upload_id)
    if not state or state.get("user_id") != user["id"]:
        raise HTTPException(404, "Unknown upload")
    blob = _chunk_blob_path(upload_id)
    if not blob.exists():
        _purge_chunk_upload(upload_id)
        raise HTTPException(400, "Upload data missing")
    received = blob.stat().st_size
    total = int(state.get("total_size") or 0)
    if received < total:
        # Don't purge here — the client may retry the missing chunks.
        raise HTTPException(400, f"Upload incomplete ({received}/{total} bytes)")

    success = False
    try:
        title = (payload.get("title") or state.get("filename") or "Untitled").strip() or "Untitled"
        description = (payload.get("description") or "").strip()
        tags = payload.get("tags") or ""
        if isinstance(tags, str):
            tags_list = [t.strip() for t in tags.split(",") if t.strip()]
        elif isinstance(tags, list):
            tags_list = [str(t).strip() for t in tags if str(t).strip()]
        else:
            tags_list = []
        category_id = payload.get("category_id") or None
        access_tier = payload.get("access_tier") or "free"
        if access_tier not in ("free", "pro", "vip"):
            access_tier = "free"
        is_short = bool(payload.get("is_short", False))

        # Move blob into the canonical originals/<id><ext> path
        vid_id = new_id()
        orig_ext = (Path(state.get("filename") or "video.mp4").suffix or ".mp4").lower()
        src_path = UPLOAD_DIR / "originals" / f"{vid_id}{orig_ext}"
        src_path.parent.mkdir(exist_ok=True, parents=True)
        blob.rename(src_path)

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
            original_filename=state.get("filename") or "",
            original_size_bytes=received,
            status="processing",
        )
        v_dict = v.model_dump()
        v_dict["slug"] = await build_video_slug(title, vid_id)
        await db.videos.insert_one(v_dict)
        v_dict.pop("_id", None)
        background.add_task(process_video, vid_id, str(src_path))
        success = True
        return v_dict
    finally:
        # ALWAYS clean up the chunk staging directory — even if the DB insert or
        # rename fails, we don't want orphaned `.chunks/<uid>/` directories on
        # disk.  When we got far enough that the blob was renamed out, the
        # rmtree is a no-op on the blob file itself but still removes state.json.
        if success:
            _purge_chunk_upload(upload_id)


@api.delete("/videos/upload/{upload_id}")
async def upload_video_abort(upload_id: str, user: dict = Depends(require_user)):
    state = _read_chunk_state(upload_id)
    if not state or state.get("user_id") != user["id"]:
        raise HTTPException(404, "Unknown upload")
    _purge_chunk_upload(upload_id)
    return {"ok": True}


# ============ Admin: pending chunked uploads janitor ============
@api.get("/admin/uploads/pending")
async def admin_list_pending_uploads(admin: dict = Depends(require_admin)):
    """List every chunk staging directory + summary stats so admin can see
    orphaned uploads at a glance."""
    items = _scan_chunk_uploads()
    total_bytes = sum(i.get("received_size", 0) for i in items)
    stale = [i for i in items if i.get("stale")]
    return {
        "items": items,
        "count": len(items),
        "stale_count": len(stale),
        "total_bytes": total_bytes,
    }


@api.post("/admin/uploads/cleanup")
async def admin_cleanup_pending_uploads(
    payload: dict = None, admin: dict = Depends(require_admin),
):
    """Purge all pending chunked uploads older than `max_age_hours` (default
    24h).  Pass `{"force": true}` to wipe ALL pending uploads regardless of
    age — useful when migrating servers."""
    payload = payload or {}
    if payload.get("force"):
        purged = 0
        for child in list(CHUNKS_DIR.iterdir()) if CHUNKS_DIR.exists() else []:
            if child.is_dir():
                _purge_chunk_upload(child.name)
                purged += 1
        return {"ok": True, "purged": purged, "mode": "force"}
    max_age = float(payload.get("max_age_hours", 24))
    purged = _cleanup_stale_chunks(max_age_hours=max_age)
    return {"ok": True, "purged": purged, "mode": "stale", "max_age_hours": max_age}


@api.patch("/videos/{video_id}")
async def update_video(
    video_id: str, req: VideoUpdateReq, user: dict = Depends(require_user)
):
    try:
        v = await find_video_by_id_or_slug(video_id)
        if not v:
            raise HTTPException(404, "Not found")
        vid = v["id"]
        uploader_id = v.get("uploader_id") or ""
        if uploader_id and uploader_id != user["id"] and user.get("role") != "admin":
            raise HTTPException(403, "Not your video")
        # Legacy migrated docs may have no uploader_id at all — allow admins
        # to edit them (non-admins can't reach this point).
        if not uploader_id and user.get("role") != "admin":
            raise HTTPException(403, "Not your video")
        upd = {k: val for k, val in req.model_dump(exclude_unset=True).items() if val is not None}
        # Validate access_tier if provided
        if "access_tier" in upd and upd["access_tier"] not in ("free", "pro", "vip"):
            raise HTTPException(400, "access_tier must be free, pro or vip")
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
        # Title change triggers slug regeneration (keeps the same trailing UUID
        # short so external links don't have to update unless title changes a lot).
        if "title" in upd and upd["title"] and upd["title"] != v.get("title"):
            upd["slug"] = await build_video_slug(upd["title"], vid)
        if upd:
            await db.videos.update_one({"id": vid}, {"$set": upd})
        # Use the normalizing helper so legacy docs without `synopsis` still
        # get the field defaulted to "" in the PATCH response.
        v = await find_video_by_id_or_slug(vid)
        return v
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        import traceback
        logger.error("PATCH /videos/%s failed: %s\n%s", video_id, e, traceback.format_exc())
        raise HTTPException(500, f"Update failed: {type(e).__name__}: {str(e)[:300]}")


@api.delete("/videos/{video_id}")
async def delete_video(video_id: str, user: dict = Depends(require_user)):
    v = await find_video_by_id_or_slug(video_id)
    if not v:
        raise HTTPException(404, "Not found")
    vid = v["id"]
    if (v.get("uploader_id") or "") != user["id"] and user.get("role") != "admin":
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
    await db.videos.delete_one({"id": vid})
    await db.comments.delete_many({"video_id": vid})
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
    v = await find_video_by_id_or_slug(video_id)
    if not v:
        return []
    # Match comments by canonical UUID, but ALSO by legacy_id so comments
    # imported during DB migration (which used the legacy numeric/string id)
    # remain visible.  Newer comments are inserted with the canonical id.
    or_keys = [v["id"]]
    if v.get("legacy_id"):
        or_keys.append(str(v["legacy_id"]))
    cs = await db.comments.find(
        {"video_id": {"$in": or_keys}}, {"_id": 0},
    ).sort("created_at", -1).to_list(500)
    # Attach the user's CURRENT selected frame (latest, not snapshot) so cadre
    # changes take effect across already-posted comments too.
    user_ids = list({c.get("user_id") for c in cs if c.get("user_id")})
    if user_ids:
        users = await db.users.find(
            {"id": {"$in": user_ids}},
            {"_id": 0, "id": 1, "selected_frame_id": 1, "avatar_url": 1},
        ).to_list(len(user_ids))
        u_by_id = {u["id"]: u for u in users}
        frame_ids = [u.get("selected_frame_id") for u in users if u.get("selected_frame_id")]
        frame_ids = list(set(frame_ids))
        frames = await db.avatar_frames.find(
            {"id": {"$in": frame_ids}}, {"_id": 0},
        ).to_list(len(frame_ids)) if frame_ids else []
        f_by_id = {f["id"]: f for f in frames}
        for c in cs:
            u = u_by_id.get(c.get("user_id"))
            if u:
                # Always refresh avatar to the latest one too
                c["avatar_url"] = u.get("avatar_url") or c.get("avatar_url")
                fid = u.get("selected_frame_id")
                if fid and fid in f_by_id:
                    c["frame"] = f_by_id[fid]
                else:
                    c["frame"] = None
    return cs


@api.post("/videos/{video_id}/comments")
async def add_comment(
    video_id: str, req: CommentReq, user: dict = Depends(require_user)
):
    if not req.content.strip():
        raise HTTPException(400, "Empty content")
    v = await find_video_by_id_or_slug(video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    vid = v["id"]
    c = Comment(
        video_id=vid,
        user_id=user["id"],
        username=user["username"],
        avatar_url=user.get("avatar_url"),
        frame_id=user.get("selected_frame_id"),
        content=req.content.strip(),
    )
    await db.comments.insert_one(c.model_dump())
    # Coin reward — capped at N comment-rewards per day per video to prevent spam
    coins_awarded = 0
    settings = await get_settings()
    amt = int(settings.get("coins_per_comment", 2) or 0)
    cap = int(settings.get("coins_comment_daily_cap_per_video", 10) or 0)
    if amt > 0 and cap > 0:
        # Count today's rewarded comments by this user on this video
        from datetime import date as _date
        today_iso_start = _date.today().isoformat()
        already = await db.coin_ledger.count_documents({
            "user_id": user["id"],
            "reason": f"comment:{vid}",
            "created_at": {"$gte": today_iso_start},
        })
        if already < cap:
            coins_awarded = amt
            await _award_coins(user["id"], amt, f"comment:{vid}")
    out = c.model_dump()
    out["coins_awarded"] = coins_awarded
    # Attach frame doc (if any) for immediate render on the client
    if user.get("selected_frame_id"):
        frame = await db.avatar_frames.find_one({"id": user["selected_frame_id"]}, {"_id": 0})
        out["frame"] = frame
    return out


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
def _normalize_package(pkg: dict) -> dict:
    """Backfill `tier="pro"` for legacy packages that predate the VIP split."""
    if pkg is not None and "tier" not in pkg:
        pkg["tier"] = "pro"
    return pkg


@api.get("/packages")
async def list_packages(tier: Optional[str] = None):
    filt: dict = {"active": True}
    if tier in ("pro", "vip"):
        # Match legacy docs (no `tier` field) as "pro" only.
        if tier == "pro":
            filt["$or"] = [{"tier": "pro"}, {"tier": {"$exists": False}}]
        else:
            filt["tier"] = "vip"
    pks = await db.packages.find(filt, {"_id": 0}).sort("sort_order", 1).to_list(20)
    return [_normalize_package(p) for p in pks]


@api.get("/packages/all")
async def list_all_packages(tier: Optional[str] = None, admin: dict = Depends(require_admin)):
    filt: dict = {}
    if tier in ("pro", "vip"):
        if tier == "pro":
            filt["$or"] = [{"tier": "pro"}, {"tier": {"$exists": False}}]
        else:
            filt["tier"] = "vip"
    pks = await db.packages.find(filt, {"_id": 0}).sort("sort_order", 1).to_list(20)
    return [_normalize_package(p) for p in pks]


@api.post("/packages")
async def create_package(payload: dict, admin: dict = Depends(require_admin)):
    count = await db.packages.count_documents({})
    if count >= 20:
        raise HTTPException(400, "Max 20 packages allowed")
    tier = (payload.get("tier") or "pro").lower()
    if tier not in ("pro", "vip"):
        tier = "pro"
    payload["tier"] = tier
    p = Package(**payload)
    await db.packages.insert_one(p.model_dump())
    return p.model_dump()


@api.patch("/packages/{pkg_id}")
async def update_package(pkg_id: str, payload: dict, admin: dict = Depends(require_admin)):
    if "tier" in payload and payload["tier"] not in ("pro", "vip"):
        raise HTTPException(400, "tier must be pro or vip")
    await db.packages.update_one({"id": pkg_id}, {"$set": payload})
    p = await db.packages.find_one({"id": pkg_id}, {"_id": 0})
    return _normalize_package(p)


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
async def admin_list_users(
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    admin: dict = Depends(require_admin),
):
    """Paginated user listing with server-side search.

    `q` matches `username` or `email` case-insensitively.  Returns a paginated
    envelope so the admin UI can render correct counts + "Load more".
    """
    filt: dict = {}
    if q and q.strip():
        import re as _re
        rex = _re.escape(q.strip())
        filt["$or"] = [
            {"username": {"$regex": rex, "$options": "i"}},
            {"email":    {"$regex": rex, "$options": "i"}},
        ]
    total = await db.users.count_documents(filt)
    limit = max(1, min(limit, 200))
    cur = (
        db.users.find(filt, {"_id": 0, "password_hash": 0, "verify_token": 0})
        .sort("created_at", -1).skip(max(0, skip)).limit(limit)
    )
    items = await cur.to_list(limit)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


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


@api.post("/admin/users/{user_id}/grant-vip")
async def admin_grant_vip(user_id: str, payload: dict, admin: dict = Depends(require_admin)):
    """Grant VIP to a user for a chosen duration.

    Body: {duration: "1day|1week|1month|permanent|custom", custom_days?: int, package_id?: str}
    """
    duration = (payload.get("duration") or "1month").lower()
    now = datetime.now(timezone.utc)
    if duration == "permanent":
        expires_iso = "permanent"
    elif duration == "1day":
        expires_iso = (now + timedelta(days=1)).isoformat()
    elif duration == "1week":
        expires_iso = (now + timedelta(days=7)).isoformat()
    elif duration == "1month":
        expires_iso = (now + timedelta(days=30)).isoformat()
    elif duration == "custom":
        expires_iso = (now + timedelta(days=int(payload.get("custom_days") or 1))).isoformat()
    else:
        raise HTTPException(400, "Invalid duration")
    upd = {"is_vip": True, "vip_expires_at": expires_iso}
    if payload.get("package_id"):
        upd["vip_package_id"] = payload["package_id"]
    await db.users.update_one({"id": user_id}, {"$set": upd})
    return {"ok": True, "vip_expires_at": expires_iso}


@api.post("/admin/users/{user_id}/revoke-vip")
async def admin_revoke_vip(user_id: str, admin: dict = Depends(require_admin)):
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"is_vip": False, "vip_expires_at": None, "vip_package_id": None}},
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
@api.get("/stats")
async def public_stats():
    """Public homepage stats — Total Videos / Views / Likes / Comments.
    Only counts ready videos (i.e. hides processing/failed)."""
    total_videos = await db.videos.count_documents({"status": "ready"})
    total_comments = await db.comments.count_documents({})
    views_agg = await db.videos.aggregate(
        [{"$match": {"status": "ready"}}, {"$group": {"_id": None, "v": {"$sum": "$views"}}}]
    ).to_list(1)
    likes_agg = await db.videos.aggregate(
        [
            {"$match": {"status": "ready"}},
            {"$project": {"c": {"$size": {"$ifNull": ["$likes", []]}}}},
            {"$group": {"_id": None, "v": {"$sum": "$c"}}},
        ]
    ).to_list(1)
    return {
        "total_videos": total_videos,
        "total_views": int(views_agg[0]["v"]) if views_agg else 0,
        "total_likes": int(likes_agg[0]["v"]) if likes_agg else 0,
        "total_comments": total_comments,
    }


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
async def admin_list_videos(
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = None,
    access_tier: Optional[str] = None,
    is_short: Optional[bool] = None,
    admin: dict = Depends(require_admin),
):
    """Paginated video listing with server-side search.

    `q` matches title, uploader_username, or tags case-insensitively.
    Additional optional filters: status_filter (ready/processing/failed),
    access_tier (free/pro), is_short (true/false).
    """
    filt: dict = {}
    if q and q.strip():
        import re as _re
        rex = _re.escape(q.strip())
        filt["$or"] = [
            {"title":              {"$regex": rex, "$options": "i"}},
            {"uploader_username":  {"$regex": rex, "$options": "i"}},
            {"tags":               {"$regex": rex, "$options": "i"}},
        ]
    if status_filter in ("ready", "processing", "failed"):
        filt["status"] = status_filter
    if access_tier in ("free", "pro", "vip"):
        filt["access_tier"] = access_tier
    if is_short is True:
        filt["is_short"] = True
    elif is_short is False:
        filt["is_short"] = {"$ne": True}
    total = await db.videos.count_documents(filt)
    limit = max(1, min(limit, 200))
    cur = (
        db.videos.find(filt, {"_id": 0})
        .sort("created_at", -1).skip(max(0, skip)).limit(limit)
    )
    items = await cur.to_list(limit)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


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
        pkg_tier = (pkg.get("tier") if pkg else "pro") or "pro"
        if pkg_tier == "vip":
            user_upd = {
                "is_vip": True,
                "vip_package_id": tx["package_id"],
                "vip_expires_at": expires_at,
            }
        else:
            user_upd = {
                "is_pro": True,
                "pro_package_id": tx["package_id"],
                "pro_expires_at": expires_at,
            }
        await db.users.update_one({"id": tx["user_id"]}, {"$set": user_upd})
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
            pkg_tier = (pkg.get("tier") if pkg else "pro") or "pro"
            if pkg_tier == "vip":
                user_upd = {
                    "is_vip": True,
                    "vip_package_id": tx["package_id"],
                    "vip_expires_at": expires_at,
                }
            else:
                user_upd = {
                    "is_pro": True,
                    "pro_package_id": tx["package_id"],
                    "pro_expires_at": expires_at,
                }
            await db.users.update_one({"id": tx["user_id"]}, {"$set": user_upd})
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

    # Boot-time cleanup of stale chunked uploads — anything older than 24h is
    # almost certainly an abandoned browser session.  Also start a periodic
    # janitor task that re-runs the cleanup every 6h so long-lived servers
    # don't accumulate orphans between restarts.
    try:
        purged = _cleanup_stale_chunks(max_age_hours=24)
        if purged:
            logger.info("[startup] purged %d stale chunked upload(s) >24h", purged)
    except Exception as e:  # noqa: BLE001
        logger.warning("[startup] stale-chunks cleanup error: %s", e)

    async def _chunks_janitor():
        while True:
            try:
                await asyncio.sleep(6 * 3600)  # 6h
                _cleanup_stale_chunks(max_age_hours=24)
            except asyncio.CancelledError:
                return
            except Exception as e:  # noqa: BLE001
                logger.warning("[janitor] error: %s", e)

    app.state.chunks_janitor = asyncio.create_task(_chunks_janitor())


@app.on_event("shutdown")
async def shutdown():
    # Cancel the background janitor task (if it was started)
    task = getattr(app.state, "chunks_janitor", None)
    if task and not task.done():
        task.cancel()
    client.close()


@api.get("/")
async def root():
    return {"message": "StreamHub API", "status": "ok"}


# ============ SUBTITLES ============
@api.post("/videos/{video_id}/subtitles")
async def add_subtitle(
    video_id: str,
    file: UploadFile = File(...),
    language: str = Form(""),
    label: str = Form(""),
    user: dict = Depends(require_user),
):
    v = await find_video_by_id_or_slug(video_id)
    if not v:
        raise HTTPException(404, "Not found")
    vid = v["id"]
    uploader_id = v.get("uploader_id") or ""
    if uploader_id and uploader_id != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your video")
    # Legacy migrated docs may have no uploader_id — admins only.
    if not uploader_id and user.get("role") != "admin":
        raise HTTPException(403, "Not your video")
    if len(v.get("subtitles", [])) >= 100:
        raise HTTPException(400, "Max 100 subtitles per video")
    # Auto-detect language + label from the filename when the caller did not
    # supply them explicitly.  Example heuristics:
    #   episode01.ja-jp.srt  → ja  → "Japanese"
    #   [ROM] sub.srt        → ro  → "Romanian"
    #   subtitle.Romanian.srt→ ro  → "Romanian"
    fname = file.filename or "sub.srt"
    if not (language or "").strip() or not (label or "").strip():
        detected = detect_language_from_filename(fname)
        if not (language or "").strip():
            language = detected["language"]
        if not (label or "").strip():
            label = detected["label"]
    if not language:
        language = "und"
    if not label:
        label = "Track"
    ext = (Path(fname).suffix or ".srt").lower()
    if ext not in (".srt", ".ass", ".vtt"):
        raise HTTPException(400, "Only .srt, .ass or .vtt allowed")
    sub_id = new_id()
    orig_name = f"{vid}_{sub_id}{ext}"
    vtt_name = f"{vid}_{sub_id}.vtt"
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
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", str(orig_path), str(vtt_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except FileNotFoundError as e:
            raise HTTPException(
                500,
                "Subtitle conversion needs ffmpeg but it is not installed on the server. "
                "Install ffmpeg (`apt install ffmpeg` inside the backend container) or upload .vtt directly.",
            ) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"Subtitle conversion failed: {type(e).__name__}: {str(e)[:200]}") from e
        if not vtt_path.exists():
            raise HTTPException(500, "Subtitle conversion produced no output (ffmpeg likely rejected the file). Try re-encoding or uploading .vtt directly.")
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
    await db.videos.update_one({"id": vid}, {"$push": {"subtitles": sub}})
    return sub


@api.post("/videos/{video_id}/extract-embedded-subs")
async def reextract_embedded_subtitles(video_id: str, user: dict = Depends(require_user)):
    """Re-run subtitle extraction on an already-processed video.

    Use this when a freshly uploaded MKV had its embedded subtitles missed
    (e.g. an ASS track with custom styling that failed the WebVTT mux on the
    original pass).  The improved 3-tier extractor lives in
    :func:`transcoder.extract_embedded_subtitles`.

    Only the video owner or an admin can trigger this.  Does NOT re-transcode
    the video — it only inspects the source file and appends any *new*
    subtitle tracks that weren't already present.
    """
    v = await find_video_by_id_or_slug(video_id)
    if not v:
        raise HTTPException(404, "Not found")
    vid = v["id"]
    if v.get("uploader_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your video")

    # Locate the source file.  After successful transcoding, the source lives
    # at UPLOAD_DIR/originals/<id>.<ext>.  We try a few extensions because the
    # stored value isn't always known at this point.
    src: Optional[Path] = None
    for ext in (".mkv", ".mp4", ".mov", ".webm", ".avi", ".ts"):
        candidate = UPLOAD_DIR / "originals" / f"{vid}{ext}"
        if candidate.exists():
            src = candidate
            break
    # Some installs may have nuked the original after Wasabi upload — try the
    # `original_filename` field too.
    if src is None and v.get("original_filename"):
        cand = UPLOAD_DIR / "originals" / v["original_filename"]
        if cand.exists():
            src = cand
    if src is None:
        raise HTTPException(
            404,
            "Source file not found locally. Re-upload required, or restore from Wasabi to /uploads/originals/.",
        )

    sub_dir = UPLOAD_DIR / "subtitles"
    sub_dir.mkdir(parents=True, exist_ok=True)
    extracted = await extract_embedded_subtitles(str(src), str(sub_dir), vid)
    if not extracted:
        return {"ok": True, "extracted": 0, "added": 0, "message": "Nicio subtitrare text găsită în sursă."}

    settings = await get_settings()
    use_wasabi = bool(settings.get("storage_provider") == "wasabi" and settings.get("wasabi_access_key"))

    # Skip tracks already present (by URL filename — embedded subs use a
    # deterministic name pattern <vid>_emb_<streamidx>_<lang>.vtt).
    existing_urls = {(s.get("url") or "") for s in (v.get("subtitles") or [])}
    new_subs: list[dict] = []
    for item in extracted:
        local_path = Path(item["rel_path"])
        rel = f"subtitles/{local_path.name}"
        if rel in existing_urls or any(rel in u for u in existing_urls):
            try:
                local_path.unlink()
            except Exception:
                pass
            continue
        final_url = rel
        if use_wasabi:
            uploaded = await wasabi_upload(
                str(local_path), rel, settings, "text/vtt; charset=utf-8",
            )
            if uploaded:
                final_url = uploaded
                try:
                    local_path.unlink()
                except Exception:
                    pass
        new_subs.append({
            "id": new_id(),
            "language": normalize_language_code(item.get("language") or "") or "und",
            "label": item.get("label") or "Track",
            "url": final_url,
            "original_url": "",
            "source": "embedded",
        })
    if new_subs:
        await db.videos.update_one({"id": vid}, {"$push": {"subtitles": {"$each": new_subs}}})
    return {
        "ok": True,
        "extracted": len(extracted),
        "added": len(new_subs),
        "skipped_duplicates": len(extracted) - len(new_subs),
    }


@api.delete("/videos/{video_id}/subtitles/{sub_id}")
async def delete_subtitle(video_id: str, sub_id: str, user: dict = Depends(require_user)):
    v = await find_video_by_id_or_slug(video_id)
    if not v:
        raise HTTPException(404, "Not found")
    vid = v["id"]
    if (v.get("uploader_id") or "") != user["id"] and user.get("role") != "admin":
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
    await db.videos.update_one({"id": vid}, {"$pull": {"subtitles": {"id": sub_id}}})
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


@api.get("/languages")
async def public_languages():
    """All ISO 639 language entries for the subtitle / language pickers."""
    return LANGUAGES


@api.get("/site/config")
async def public_site_config():
    """Public site identity / SEO + localisation + chat config consumed by the frontend."""
    s = await get_settings()
    return {
        "title": s.get("site_title") or "StreamHub",
        "description": s.get("site_description") or "",
        "favicon_url": s.get("site_favicon_url") or "",
        "logo_url": s.get("site_logo_url") or "",
        "og_image": s.get("site_og_image") or "",
        "canonical_url": s.get("site_canonical_url") or "",
        "keywords": s.get("site_seo_keywords") or "",
        "meta": s.get("site_seo_meta") or "",
        "default_language": s.get("default_language") or "ro",
        "shorts_max_duration_sec": int(s.get("shorts_max_duration_sec", 60)),
        "live_chat_enabled": bool(s.get("live_chat_enabled", True)),
        "live_chat_guest_allowed": bool(s.get("live_chat_guest_allowed", True)),
        "live_chat_max_message_length": int(s.get("live_chat_max_message_length", 500)),
        "coins_per_like": int(s.get("coins_per_like", 1)),
        "coins_per_comment": int(s.get("coins_per_comment", 2)),
        "coins_comment_daily_cap_per_video": int(s.get("coins_comment_daily_cap_per_video", 10)),
        "home_hero_text": s.get("home_hero_text") or "",
        "bulk_upload_enabled": bool(s.get("bulk_upload_enabled", True)),
        "bulk_upload_concurrency": int(s.get("bulk_upload_concurrency", 3)),
        "chunk_upload_chunk_size_mb": int(s.get("chunk_upload_chunk_size_mb", 25)),
        "max_upload_size_mb": int(s.get("max_upload_size_mb", 1024)),
        "discord_widget_enabled": bool(s.get("discord_widget_enabled", True)),
        "discord_invite_url": s.get("discord_invite_url") or "https://discord.gg/5dGdSbzT4E",
        "discord_guild_id": s.get("discord_guild_id") or "",
    }


# ============ Shop / Avatar Frames ============
@api.get("/shop/leaderboard")
async def shop_leaderboard(limit: int = 10, viewer: Optional[dict] = Depends(current_user)):
    """Public top-N users sorted by `coins`.  Also returns the viewer's rank
    (1-based) and a snapshot of their entry so the UI can render "Tu ești pe
    locul 47" when they aren't in the top N.
    """
    limit = max(1, min(50, int(limit or 10)))
    # Top-N by coins (admins ARE included — they earn coins like everyone else)
    top = await db.users.find(
        {},
        {"_id": 0, "id": 1, "username": 1, "avatar_url": 1, "coins": 1,
         "selected_frame_id": 1, "is_pro": 1},
    ).sort("coins", -1).limit(limit).to_list(limit)
    # Attach selected_frame doc for visual rendering
    frame_ids = list({u.get("selected_frame_id") for u in top if u.get("selected_frame_id")})
    f_by_id: dict = {}
    if frame_ids:
        frames = await db.avatar_frames.find({"id": {"$in": frame_ids}}, {"_id": 0}).to_list(len(frame_ids))
        f_by_id = {f["id"]: f for f in frames}
    for i, u in enumerate(top, start=1):
        u["rank"] = i
        u["selected_frame"] = f_by_id.get(u.get("selected_frame_id"))
    # Viewer's rank (count of users strictly above + 1)
    me_rank: Optional[int] = None
    me_entry: Optional[dict] = None
    if viewer:
        my_coins = int(viewer.get("coins", 0) or 0)
        above = await db.users.count_documents({"coins": {"$gt": my_coins}})
        me_rank = above + 1
        me_entry = {
            "rank": me_rank,
            "id": viewer["id"],
            "username": viewer["username"],
            "avatar_url": viewer.get("avatar_url"),
            "coins": my_coins,
            "selected_frame_id": viewer.get("selected_frame_id"),
            "is_pro": bool(viewer.get("is_pro")),
        }
        if viewer.get("selected_frame_id"):
            me_entry["selected_frame"] = await db.avatar_frames.find_one(
                {"id": viewer["selected_frame_id"]}, {"_id": 0},
            )
    return {"top": top, "me": me_entry}


@api.get("/shop/frames")
async def shop_frames(user: Optional[dict] = Depends(current_user)):
    """List all frames active in the shop, plus which ones the viewer owns."""
    frames = await db.avatar_frames.find({"active": True}, {"_id": 0}).sort("sort_order", 1).to_list(500)
    owned = set((user or {}).get("owned_frames", []) or [])
    for f in frames:
        f["owned"] = f["id"] in owned
    return frames


@api.post("/shop/frames/{frame_id}/purchase")
async def shop_purchase_frame(frame_id: str, user: dict = Depends(require_user)):
    f = await db.avatar_frames.find_one({"id": frame_id, "active": True}, {"_id": 0})
    if not f:
        raise HTTPException(404, "Frame not available")
    if frame_id in (user.get("owned_frames") or []):
        raise HTTPException(400, "Already owned")
    price = int(f.get("price_coins", 0))
    if int(user.get("coins", 0)) < price:
        raise HTTPException(402, "Not enough coins")
    # Atomic: only debit if balance still high enough
    res = await db.users.update_one(
        {"id": user["id"], "coins": {"$gte": price}},
        {"$inc": {"coins": -price}, "$addToSet": {"owned_frames": frame_id}},
    )
    if res.modified_count != 1:
        raise HTTPException(402, "Not enough coins")
    await db.coin_ledger.insert_one({
        "id": new_id(),
        "user_id": user["id"],
        "delta": -price,
        "reason": f"purchase:{frame_id}",
        "balance_after": int(user.get("coins", 0)) - price,
        "created_at": now_iso(),
    })
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {"ok": True, "user": await public_user_with_frame(u, include_email=True)}


@api.post("/users/me/selected-frame")
async def set_selected_frame(payload: dict, user: dict = Depends(require_user)):
    """Apply (or clear with null) a frame the user already owns."""
    frame_id = payload.get("frame_id")
    if frame_id and frame_id not in (user.get("owned_frames") or []):
        raise HTTPException(403, "Frame not owned")
    await db.users.update_one({"id": user["id"]}, {"$set": {"selected_frame_id": frame_id or None}})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return await public_user_with_frame(u, include_email=True)


# ============ Admin: Avatar Frames CRUD ============
@api.get("/admin/frames")
async def admin_list_frames(admin: dict = Depends(require_admin)):
    return await db.avatar_frames.find({}, {"_id": 0}).sort("sort_order", 1).to_list(500)


@api.post("/admin/frames")
async def admin_create_frame(payload: dict, admin: dict = Depends(require_admin)):
    f = AvatarFrame(
        name=(payload.get("name") or "Frame").strip(),
        effect_key=(payload.get("effect_key") or "neon-ring").strip(),
        color_primary=(payload.get("color_primary") or "#f43f5e").strip(),
        color_secondary=(payload.get("color_secondary") or "#fb7185").strip(),
        rarity=(payload.get("rarity") or "common").strip(),
        price_coins=int(payload.get("price_coins") or 0),
        active=bool(payload.get("active", True)),
        sort_order=int(payload.get("sort_order") or 0),
    )
    await db.avatar_frames.insert_one(f.model_dump())
    return f.model_dump()


@api.patch("/admin/frames/{frame_id}")
async def admin_update_frame(frame_id: str, payload: dict, admin: dict = Depends(require_admin)):
    upd: dict = {}
    for k in ("name", "effect_key", "color_primary", "color_secondary", "rarity"):
        if k in payload and payload[k] is not None:
            upd[k] = str(payload[k]).strip()
    if "price_coins" in payload:
        upd["price_coins"] = int(payload["price_coins"] or 0)
    if "active" in payload:
        upd["active"] = bool(payload["active"])
    if "sort_order" in payload:
        upd["sort_order"] = int(payload["sort_order"] or 0)
    if upd:
        await db.avatar_frames.update_one({"id": frame_id}, {"$set": upd})
    f = await db.avatar_frames.find_one({"id": frame_id}, {"_id": 0})
    if not f:
        raise HTTPException(404, "Not found")
    return f


@api.delete("/admin/frames/{frame_id}")
async def admin_delete_frame(frame_id: str, admin: dict = Depends(require_admin)):
    await db.avatar_frames.delete_one({"id": frame_id})
    # Also remove from users' inventories (refund-free; admin choice)
    await db.users.update_many(
        {"owned_frames": frame_id},
        {"$pull": {"owned_frames": frame_id}},
    )
    await db.users.update_many(
        {"selected_frame_id": frame_id},
        {"$set": {"selected_frame_id": None}},
    )
    return {"ok": True}


@api.post("/admin/frames/seed")
async def admin_frames_seed(admin: dict = Depends(require_admin)):
    """Seed the 50 default CSS-animated frames (idempotent: only inserts missing names)."""
    existing = {f["name"] for f in await db.avatar_frames.find({}, {"_id": 0, "name": 1}).to_list(1000)}
    inserted = 0
    for i, spec in enumerate(_DEFAULT_FRAMES):
        if spec["name"] in existing:
            continue
        f = AvatarFrame(
            name=spec["name"],
            effect_key=spec["effect_key"],
            color_primary=spec["color_primary"],
            color_secondary=spec["color_secondary"],
            rarity=spec["rarity"],
            price_coins=spec["price_coins"],
            sort_order=i,
        )
        await db.avatar_frames.insert_one(f.model_dump())
        inserted += 1
    return {"ok": True, "inserted": inserted, "total": await db.avatar_frames.count_documents({})}


# 50 default frames inspired by the Steam Points Shop avatar frame categories.
# Each `effect_key` maps to a CSS animation owned by the React `FramedAvatar`.
_DEFAULT_FRAMES = [
    # Common (50–150)
    {"name": "Inel Neon Roz",      "effect_key": "neon-ring",      "color_primary": "#f43f5e", "color_secondary": "#fb7185", "rarity": "common", "price_coins": 50},
    {"name": "Inel Neon Cyan",     "effect_key": "neon-ring",      "color_primary": "#06b6d4", "color_secondary": "#22d3ee", "rarity": "common", "price_coins": 50},
    {"name": "Inel Neon Verde",    "effect_key": "neon-ring",      "color_primary": "#22c55e", "color_secondary": "#86efac", "rarity": "common", "price_coins": 50},
    {"name": "Inel Neon Violet",   "effect_key": "neon-ring",      "color_primary": "#8b5cf6", "color_secondary": "#c4b5fd", "rarity": "common", "price_coins": 50},
    {"name": "Inel Neon Galben",   "effect_key": "neon-ring",      "color_primary": "#eab308", "color_secondary": "#fde047", "rarity": "common", "price_coins": 50},
    {"name": "Dashed Pulse Roz",   "effect_key": "dashed-rotate",  "color_primary": "#f472b6", "color_secondary": "#fda4af", "rarity": "common", "price_coins": 80},
    {"name": "Dashed Pulse Blue",  "effect_key": "dashed-rotate",  "color_primary": "#3b82f6", "color_secondary": "#93c5fd", "rarity": "common", "price_coins": 80},
    {"name": "Glow Suav Coral",    "effect_key": "soft-glow",      "color_primary": "#fb923c", "color_secondary": "#fdba74", "rarity": "common", "price_coins": 60},
    {"name": "Glow Suav Lime",     "effect_key": "soft-glow",      "color_primary": "#84cc16", "color_secondary": "#bef264", "rarity": "common", "price_coins": 60},
    {"name": "Glow Suav Magenta",  "effect_key": "soft-glow",      "color_primary": "#ec4899", "color_secondary": "#f9a8d4", "rarity": "common", "price_coins": 60},
    # Rare (200–400)
    {"name": "Conic Rainbow",      "effect_key": "conic-rotate",   "color_primary": "#f43f5e", "color_secondary": "#3b82f6", "rarity": "rare",   "price_coins": 220},
    {"name": "Conic Ocean",        "effect_key": "conic-rotate",   "color_primary": "#0ea5e9", "color_secondary": "#22d3ee", "rarity": "rare",   "price_coins": 220},
    {"name": "Conic Sunset",       "effect_key": "conic-rotate",   "color_primary": "#f59e0b", "color_secondary": "#ef4444", "rarity": "rare",   "price_coins": 220},
    {"name": "Conic Aurora",       "effect_key": "conic-rotate",   "color_primary": "#10b981", "color_secondary": "#8b5cf6", "rarity": "rare",   "price_coins": 250},
    {"name": "Stele Cosmice",      "effect_key": "stars-orbit",    "color_primary": "#fde047", "color_secondary": "#ffffff", "rarity": "rare",   "price_coins": 300},
    {"name": "Stele Negre",        "effect_key": "stars-orbit",    "color_primary": "#a855f7", "color_secondary": "#f9a8d4", "rarity": "rare",   "price_coins": 300},
    {"name": "Pulse Cardiac",      "effect_key": "pulse-shadow",   "color_primary": "#ef4444", "color_secondary": "#fca5a5", "rarity": "rare",   "price_coins": 250},
    {"name": "Pulse Frost",        "effect_key": "pulse-shadow",   "color_primary": "#3b82f6", "color_secondary": "#bfdbfe", "rarity": "rare",   "price_coins": 250},
    {"name": "Aurora Glow",        "effect_key": "aurora-shift",   "color_primary": "#22c55e", "color_secondary": "#06b6d4", "rarity": "rare",   "price_coins": 320},
    {"name": "Aurora Purpurie",    "effect_key": "aurora-shift",   "color_primary": "#a855f7", "color_secondary": "#ec4899", "rarity": "rare",   "price_coins": 320},
    # Epic (500–900)
    {"name": "Foc Înflăcărat",     "effect_key": "fire",           "color_primary": "#f97316", "color_secondary": "#facc15", "rarity": "epic",   "price_coins": 600},
    {"name": "Foc Albastru",       "effect_key": "fire",           "color_primary": "#1d4ed8", "color_secondary": "#22d3ee", "rarity": "epic",   "price_coins": 650},
    {"name": "Foc Verde Toxic",    "effect_key": "fire",           "color_primary": "#16a34a", "color_secondary": "#bef264", "rarity": "epic",   "price_coins": 650},
    {"name": "Electric Storm",     "effect_key": "electric",       "color_primary": "#facc15", "color_secondary": "#fff7d6", "rarity": "epic",   "price_coins": 700},
    {"name": "Electric Mov",       "effect_key": "electric",       "color_primary": "#a855f7", "color_secondary": "#e9d5ff", "rarity": "epic",   "price_coins": 700},
    {"name": "Particule Aurii",    "effect_key": "particles",      "color_primary": "#facc15", "color_secondary": "#fef3c7", "rarity": "epic",   "price_coins": 750},
    {"name": "Particule Argintii", "effect_key": "particles",      "color_primary": "#e5e7eb", "color_secondary": "#ffffff", "rarity": "epic",   "price_coins": 750},
    {"name": "Particule Rubin",    "effect_key": "particles",      "color_primary": "#dc2626", "color_secondary": "#fecaca", "rarity": "epic",   "price_coins": 750},
    {"name": "Hologramă",          "effect_key": "hologram",       "color_primary": "#06b6d4", "color_secondary": "#a855f7", "rarity": "epic",   "price_coins": 800},
    {"name": "Glitch Cyber",       "effect_key": "glitch",         "color_primary": "#22d3ee", "color_secondary": "#ec4899", "rarity": "epic",   "price_coins": 850},
    # Legendary (1000–2500)
    {"name": "Strălucire Aurie",   "effect_key": "gold-shimmer",   "color_primary": "#facc15", "color_secondary": "#fef9c3", "rarity": "legendary", "price_coins": 1200},
    {"name": "Strălucire Diamant", "effect_key": "diamond-shimmer", "color_primary": "#bae6fd", "color_secondary": "#ffffff", "rarity": "legendary", "price_coins": 1500},
    {"name": "Inel de Foc",        "effect_key": "fire-ring",      "color_primary": "#ea580c", "color_secondary": "#fcd34d", "rarity": "legendary", "price_coins": 1400},
    {"name": "Inel de Gheață",     "effect_key": "frost-ring",     "color_primary": "#7dd3fc", "color_secondary": "#e0f2fe", "rarity": "legendary", "price_coins": 1400},
    {"name": "Drăgăstos",          "effect_key": "hearts-orbit",   "color_primary": "#ef4444", "color_secondary": "#fda4af", "rarity": "legendary", "price_coins": 1300},
    {"name": "Lună Plină",         "effect_key": "moon-glow",      "color_primary": "#fcd34d", "color_secondary": "#fde68a", "rarity": "legendary", "price_coins": 1300},
    {"name": "Coroană Regală",     "effect_key": "crown-orbit",    "color_primary": "#facc15", "color_secondary": "#fef3c7", "rarity": "legendary", "price_coins": 1800},
    {"name": "Demonic",            "effect_key": "demonic",        "color_primary": "#7f1d1d", "color_secondary": "#dc2626", "rarity": "legendary", "price_coins": 1700},
    {"name": "Galactic",           "effect_key": "galaxy",         "color_primary": "#312e81", "color_secondary": "#a855f7", "rarity": "legendary", "price_coins": 2000},
    {"name": "Nebula Roz",         "effect_key": "galaxy",         "color_primary": "#831843", "color_secondary": "#f472b6", "rarity": "legendary", "price_coins": 2000},
    {"name": "Soare",              "effect_key": "sun-rays",       "color_primary": "#f59e0b", "color_secondary": "#fde047", "rarity": "legendary", "price_coins": 1900},
    {"name": "Phoenix",            "effect_key": "phoenix",        "color_primary": "#dc2626", "color_secondary": "#fb923c", "rarity": "legendary", "price_coins": 2200},
    {"name": "Dragon Verde",       "effect_key": "dragon-scales",  "color_primary": "#16a34a", "color_secondary": "#65a30d", "rarity": "legendary", "price_coins": 2100},
    {"name": "Dragon Roșu",        "effect_key": "dragon-scales",  "color_primary": "#dc2626", "color_secondary": "#f59e0b", "rarity": "legendary", "price_coins": 2100},
    {"name": "Sakura",             "effect_key": "petals",         "color_primary": "#f9a8d4", "color_secondary": "#fce7f3", "rarity": "legendary", "price_coins": 1600},
    {"name": "Frunze de Toamnă",   "effect_key": "petals",         "color_primary": "#ea580c", "color_secondary": "#facc15", "rarity": "legendary", "price_coins": 1600},
    {"name": "Cyber Punk",         "effect_key": "cyberpunk",      "color_primary": "#22d3ee", "color_secondary": "#ec4899", "rarity": "legendary", "price_coins": 2400},
    {"name": "Matrix",             "effect_key": "matrix",         "color_primary": "#16a34a", "color_secondary": "#86efac", "rarity": "legendary", "price_coins": 2300},
    {"name": "Lava",               "effect_key": "lava",           "color_primary": "#dc2626", "color_secondary": "#fbbf24", "rarity": "legendary", "price_coins": 2200},
    {"name": "Cosmos Suprem",      "effect_key": "cosmos-supreme", "color_primary": "#a855f7", "color_secondary": "#fde047", "rarity": "legendary", "price_coins": 2500},
]


@api.get("/og/video/{video_id}")
async def og_video_html(video_id: str, request: Request):
    """Server-rendered HTML for social-media crawlers (Discord/Facebook/Twitter/etc).

    Always returns absolute URLs (Facebook requires it).  Falls back to the
    Host header from the request when no canonical_url is configured.
    """
    from fastapi.responses import HTMLResponse
    import html as _html
    v = await find_video_by_id_or_slug(video_id)
    s = await get_settings()
    site_title = s.get("site_title") or "StreamHub"
    # Prefer configured canonical, else build from the incoming request — that
    # way OG cards work even when the admin hasn't set Site/SEO yet.
    base = (s.get("site_canonical_url") or "").rstrip("/")
    if not base:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        host = request.headers.get("host") or request.url.hostname or ""
        if host:
            base = f"{proto}://{host}"
    if not v:
        title = site_title
        desc = s.get("site_description") or ""
        img = _absolute_og_image(s.get("site_og_image") or "", base)
        page_url = base or "/"
    else:
        title = f'{v.get("title") or "Video"} — {site_title}'
        desc = (v.get("description") or "").strip()[:200] or (s.get("site_description") or "")
        img = _absolute_og_image(v.get("thumbnail_url") or s.get("site_og_image") or "", base)
        # Canonical URL must ALWAYS point to the slug-based URL, regardless
        # of whether Googlebot arrived via /watch/<uuid>, /watch/<legacy_id>
        # or /watch/<slug>.  Otherwise Google marks the alt URLs as
        # "Duplicate without user-selected canonical".
        canonical_slug = v.get("slug") or v["id"]
        page_url = f"{base}/watch/{canonical_slug}" if base else f"/watch/{canonical_slug}"
    esc = _html.escape
    image_tags = ""
    if img:
        image_tags = (
            f'<meta property="og:image" content="{esc(img)}">\n'
            f'<meta property="og:image:secure_url" content="{esc(img)}">\n'
            f'<meta property="og:image:width" content="1280">\n'
            f'<meta property="og:image:height" content="720">\n'
            f'<meta name="twitter:image" content="{esc(img)}">\n'
        )
    # Keywords: combine the admin-configured `site_seo_keywords` with the
    # per-video tags so each episode appears in Google for searches that
    # match either the global keywords OR the episode-specific tags.
    site_kw = (s.get("site_seo_keywords") or "").strip()
    video_kw_parts: List[str] = []
    if v:
        for t in (v.get("tags") or []):
            t = str(t).strip()
            if t:
                video_kw_parts.append(t)
        if v.get("title"):
            video_kw_parts.append(v["title"])
    all_kw = ", ".join([k for k in ([site_kw] + video_kw_parts) if k])
    keywords_tag = f'<meta name="keywords" content="{esc(all_kw)}">\n' if all_kw else ""
    # ---------------------------------------------------------------------
    # Build a SEO-rich `<body>` with the actual video content so Googlebot has
    # something to rank.  The previous version was nearly empty + had a
    # client meta-refresh which Google interprets as "this page redirects,
    # index the target instead" — killing per-episode indexing.
    # ---------------------------------------------------------------------
    tags_html = ""
    if v and v.get("tags"):
        tags_html = "<p><strong>Tags:</strong> " + ", ".join(esc(t) for t in v["tags"]) + "</p>"

    # Synopsis — long-form plot summary that gives Googlebot substantially
    # more unique per-page text.  When populated by the admin this alone
    # tends to move episodes from "Crawled - not indexed" to "Indexed".
    synopsis_html = ""
    if v and (v.get("synopsis") or "").strip():
        synopsis_html = f'<section><h2>Sinopsis</h2><p>{esc(v["synopsis"])}</p></section>'

    # Top 5 comments — user-generated content is a strong quality signal
    # for Google.  Rendered as static HTML so Googlebot sees them without JS.
    comments_html = ""
    if v:
        try:
            top_comments = await db.comments.find(
                {"video_id": v["id"]},
                {"_id": 0, "username": 1, "content": 1, "created_at": 1},
            ).sort("created_at", -1).limit(5).to_list(5)
            if top_comments:
                items = []
                for c in top_comments:
                    author = esc(c.get("username") or "user")
                    body_text = esc((c.get("content") or "").strip()[:600])
                    when = esc((c.get("created_at") or "")[:10])
                    items.append(
                        f'<li><strong>{author}</strong> <time>{when}</time><p>{body_text}</p></li>'
                    )
                comments_html = (
                    "<section><h2>Comentarii</h2><ul>" + "".join(items) + "</ul></section>"
                )
        except Exception:
            pass

    # Related videos — gives Googlebot internal links between episodes,
    # which compounds your site's internal PageRank.
    related_html: list[str] = []
    if v:
        try:
            related = await db.videos.find(
                {"status": "ready", "id": {"$ne": v["id"]}},
                {"_id": 0, "id": 1, "slug": 1, "title": 1, "thumbnail_url": 1},
            ).sort("created_at", -1).limit(10).to_list(10)
            for rv in related:
                rlink = f"{base}/watch/{rv.get('slug') or rv['id']}" if base else f"/watch/{rv.get('slug') or rv['id']}"
                rimg = mediaUrl_for_og(rv.get("thumbnail_url") or "", s)
                related_html.append(
                    f'<li><a href="{esc(rlink)}"><img src="{esc(rimg)}" '
                    f'alt="{esc(rv["title"])}" width="220" height="124" loading="lazy"></a>'
                    f'<a href="{esc(rlink)}">{esc(rv["title"])}</a></li>'
                )
        except Exception:
            pass

    # Schema.org VideoObject JSON-LD — what powers Google's video carousel
    # and rich snippets.  Requires absolute URLs.
    json_ld = ""
    if v:
        from datetime import datetime as _dt
        ld = {
            "@context": "https://schema.org",
            "@type": "VideoObject",
            "name": v.get("title") or "",
            "description": (v.get("description") or "")[:5000] or v.get("title") or "",
            "thumbnailUrl": img or None,
            "uploadDate": (v.get("created_at") or _dt.utcnow().isoformat()),
            "contentUrl": page_url,
            "embedUrl": page_url,
        }
        if v.get("duration_sec"):
            d = int(v["duration_sec"])
            ld["duration"] = f"PT{d // 3600}H{(d % 3600) // 60}M{d % 60}S"
        import json as _json
        json_ld = f'<script type="application/ld+json">{_json.dumps({k: v_ for k, v_ in ld.items() if v_ is not None}, ensure_ascii=False)}</script>'

    body = f"""<!doctype html>
<html lang="ro"><head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{keywords_tag}<link rel="canonical" href="{esc(page_url)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta property="og:type" content="video.other">
<meta property="og:site_name" content="{esc(site_title)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(page_url)}">
{image_tags}<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
{json_ld}
</head>
<body>
<header>
  <h1>{esc(v.get("title") if v else title)}</h1>
  {f'<img src="{esc(img)}" alt="{esc(v.get("title") or "")}" width="1280" height="720">' if (img and v) else ""}
</header>
<article>
  <p>{esc(desc or v.get("title") or "") if v else esc(desc)}</p>
  {synopsis_html}
  {tags_html}
  <p><a href="{esc(page_url)}">Vizionează episodul →</a></p>
</article>
{comments_html}
<aside>
  <h2>Episoade asemănătoare</h2>
  <ul>{''.join(related_html)}</ul>
</aside>
</body></html>"""
    return HTMLResponse(
        body,
        status_code=200,
        headers={
            "Cache-Control": "public, max-age=300",
            # Stop CDNs from echoing 206 Partial Content for HTML when the
            # crawler sends a Range header — Facebook's debugger reports the
            # 206 as a warning that confuses other validators.
            "Accept-Ranges": "none",
            "Content-Type": "text/html; charset=utf-8",
        },
    )


def _absolute_og_image(rel: str, base_url: str) -> str:
    """Return a full http(s):// URL for an og:image value.  Facebook rejects relative paths."""
    if not rel:
        return ""
    if rel.startswith("http://") or rel.startswith("https://"):
        return rel
    if not base_url:
        return ""
    # Thumbnails live under /api/media/<path>; logo etc. are served the same way.
    return f"{base_url}/api/media/{rel.lstrip('/')}"


# kept for backwards compat — old name still callable, but routes use the new helper above
def mediaUrl_for_og(rel: str, settings: dict) -> str:
    return _absolute_og_image(rel, (settings.get("site_canonical_url") or "").rstrip("/"))


@api.get("/og/home")
async def og_home_html():
    """SSR OG card for the homepage / unknown routes."""
    from fastapi.responses import HTMLResponse
    import html as _html
    s = await get_settings()
    title = s.get("site_title") or "StreamHub"
    desc = s.get("site_description") or ""
    base = (s.get("site_canonical_url") or "").rstrip("/")
    img = mediaUrl_for_og(s.get("site_og_image") or "", s)
    page_url = base or "/"
    esc = _html.escape

    # Build a server-rendered list of the latest 20 ready videos so Googlebot
    # actually has CONTENT to index — the SPA's client-rendered grid is
    # invisible to Search engines that don't execute JS aggressively.
    recent_html: list[str] = []
    try:
        recent = await db.videos.find(
            {"status": "ready"},
            {"_id": 0, "id": 1, "title": 1, "slug": 1, "description": 1, "thumbnail_url": 1, "tags": 1},
        ).sort("created_at", -1).limit(20).to_list(20)
        for v in recent:
            link = f"{base}/watch/{v.get('slug') or v['id']}"
            img_abs = mediaUrl_for_og(v.get("thumbnail_url") or "", s)
            recent_html.append(
                f'<li><a href="{esc(link)}"><img src="{esc(img_abs)}" alt="{esc(v["title"])}" '
                f'width="320" height="180" loading="lazy"></a>'
                f'<h2><a href="{esc(link)}">{esc(v["title"])}</a></h2>'
                f'<p>{esc((v.get("description") or "")[:200])}</p></li>'
            )
    except Exception:
        pass

    # Also expose categories so they get crawled.
    cats_html: list[str] = []
    try:
        cats = await db.categories.find({}, {"_id": 0, "name": 1, "slug": 1}).to_list(200)
        for c in cats:
            cats_html.append(
                f'<li><a href="{esc(base)}/category/{esc(c["slug"])}">{esc(c["name"])}</a></li>'
            )
    except Exception:
        pass

    body = f"""<!doctype html>
<html lang="ro"><head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{(f'<meta name="keywords" content="{esc(s.get("site_seo_keywords") or "")}">' + chr(10)) if s.get("site_seo_keywords") else ""}<link rel="canonical" href="{esc(page_url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(title)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(page_url)}">
<meta property="og:image" content="{esc(img)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{esc(img)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="sitemap" type="application/xml" href="{esc(base)}/sitemap.xml">
</head>
<body>
<h1>{esc(title)}</h1>
<p>{esc(desc)}</p>
<nav><h2>Categorii</h2><ul>{''.join(cats_html)}</ul></nav>
<section><h2>Episoade recente</h2><ul>{''.join(recent_html)}</ul></section>
<p><a href="{esc(page_url)}">Deschide site-ul →</a></p>
</body></html>"""
    return HTMLResponse(
        body,
        status_code=200,
        headers={
            "Cache-Control": "public, max-age=600",
            "Accept-Ranges": "none",
            "Content-Type": "text/html; charset=utf-8",
        },
    )


@api.get("/og/category/{cat_ref}")
async def og_category_html(cat_ref: str, request: Request):
    """SSR OG page for a category — indexed as a listing hub by Googlebot.

    Accepts either the numeric/UUID id or the slug.  Renders the category
    name in `<title>` and lists up to 40 recent videos in that category so
    Google has substantial content to consider for indexing.
    """
    from fastapi.responses import HTMLResponse
    import html as _html
    s = await get_settings()
    site_title = s.get("site_title") or "StreamHub"
    base = (s.get("site_canonical_url") or "").rstrip("/")
    esc = _html.escape

    # Look up category by id or slug
    cat = await db.categories.find_one(
        {"$or": [{"id": cat_ref}, {"slug": cat_ref}]},
        {"_id": 0, "id": 1, "name": 1, "slug": 1},
    )
    if not cat:
        # Category not found → fall back to homepage SSR
        return await og_home_html()

    cat_name = cat.get("name") or "Category"
    canonical = f"{base}/category/{cat.get('slug') or cat['id']}"
    page_title = f"{cat_name} — {site_title}"
    desc = f"Toate episoadele din categoria {cat_name} pe {site_title}."
    img = mediaUrl_for_og(s.get("site_og_image") or "", s)

    # List up to 40 recent videos in this category
    vids_html: list[str] = []
    try:
        vids = await db.videos.find(
            {"status": "ready", "category_id": cat["id"]},
            {"_id": 0, "id": 1, "title": 1, "slug": 1, "description": 1, "thumbnail_url": 1},
        ).sort("created_at", -1).limit(40).to_list(40)
        for v in vids:
            link = f"{base}/watch/{v.get('slug') or v['id']}"
            thumb = v.get("thumbnail_url")
            img_tag = ""
            if thumb:
                img_abs = mediaUrl_for_og(thumb, s)
                if img_abs:
                    img_tag = (
                        f'<a href="{esc(link)}"><img src="{esc(img_abs)}" alt="{esc(v["title"])}" '
                        f'width="320" height="180" loading="lazy"></a>'
                    )
            vids_html.append(
                f'<li>{img_tag}'
                f'<h3><a href="{esc(link)}">{esc(v["title"])}</a></h3>'
                f'<p>{esc((v.get("description") or "")[:180])}</p></li>'
            )
    except Exception:
        pass

    og_img_tag = f'<meta property="og:image" content="{esc(img)}">\n<meta name="twitter:image" content="{esc(img)}">' if img else ''

    body = f"""<!doctype html>
<html lang="ro"><head>
<meta charset="utf-8">
<title>{esc(page_title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(site_title)}">
<meta property="og:title" content="{esc(page_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
{og_img_tag}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(page_title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-image-preview:large">
</head>
<body>
<h1>{esc(cat_name)}</h1>
<p>{esc(desc)}</p>
<section><h2>Episoade</h2><ul>{''.join(vids_html)}</ul></section>
<p><a href="{esc(canonical)}">Deschide categoria →</a></p>
</body></html>"""
    return HTMLResponse(
        body,
        status_code=200,
        headers={
            "Cache-Control": "public, max-age=600",
            "Content-Type": "text/html; charset=utf-8",
        },
    )


# ============ SEO: Google Search Console dashboard ============
@api.post("/admin/seo/credentials")
async def admin_seo_save_credentials(payload: dict, admin: dict = Depends(require_admin)):
    """Save the service-account JSON key + GSC site URL.

    Validation is lightweight — we only parse the JSON, verify the email looks
    like a service account, and run a smoke `searchanalytics.query` so the
    admin gets immediate feedback if the credentials don't have access to the
    property yet.
    """
    site_url = (payload.get("site_url") or "").strip()
    sa_raw = (payload.get("service_account_json") or "").strip()
    if not site_url or not sa_raw:
        raise HTTPException(400, "site_url and service_account_json are required")
    try:
        sa = json.loads(sa_raw)
    except Exception:
        raise HTTPException(400, "service_account_json is not valid JSON")
    if sa.get("type") != "service_account":
        raise HTTPException(400, "JSON does not look like a service-account key (type≠service_account)")
    client_email = sa.get("client_email") or ""
    # Smoke test — try a 1-day query to confirm the SA has access
    err = await _gsc_smoke_test(sa, site_url)
    await db.settings.update_one(
        {"_id": "main"},
        {"$set": {"gsc_service_account_json": sa_raw, "gsc_site_url": site_url}},
        upsert=True,
    )
    return {
        "ok": True,
        "client_email": client_email,
        "site_url": site_url,
        "smoke_test_error": err,  # null on success; string with the error otherwise
    }


@api.delete("/admin/seo/credentials")
async def admin_seo_delete_credentials(admin: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"_id": "main"},
        {"$set": {"gsc_service_account_json": "", "gsc_site_url": ""}},
        upsert=True,
    )
    return {"ok": True}


@api.get("/admin/seo/dashboard")
async def admin_seo_dashboard(days: int = 28, admin: dict = Depends(require_admin)):
    """Fetch Google Search Console analytics for the configured site.

    Returns aggregated totals, top pages, top queries, and a list of every
    `/watch/<slug>` from our DB that has 0 impressions in the time window
    ("zombie" pages — Google hasn't indexed them yet).
    """
    s = await get_settings()
    sa_raw = s.get("gsc_service_account_json") or ""
    site_url = s.get("gsc_site_url") or ""
    if not sa_raw or not site_url:
        raise HTTPException(400, "Google Search Console credentials not configured.")
    try:
        sa = json.loads(sa_raw)
    except Exception:
        raise HTTPException(500, "Stored GSC credentials are corrupt; please re-upload.")
    days = max(1, min(90, int(days or 28)))
    return await _gsc_query_dashboard(sa, site_url, days)


async def _gsc_smoke_test(sa: dict, site_url: str) -> Optional[str]:
    """Run a tiny GSC query to detect setup errors early. Returns the error
    string when the SA can't access the property, else None.
    """
    try:
        await _gsc_query_dashboard(sa, site_url, days=1, max_rows=1)
        return None
    except HTTPException as e:
        return str(e.detail)
    except Exception as e:  # noqa: BLE001
        return str(e)


async def _gsc_query_dashboard(sa: dict, site_url: str, days: int, max_rows: int = 100) -> dict:
    """Call the Search Console searchanalytics.query endpoint.  Runs in a
    thread-pool because the google-api-python-client is synchronous.
    """
    from datetime import date, timedelta

    def _run():
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_info(
            sa, scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        )
        svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        end = date.today()
        start = end - timedelta(days=days)
        common = {"startDate": start.isoformat(), "endDate": end.isoformat(), "rowLimit": max_rows}
        # Three parallel calls (in this thread)
        totals = svc.searchanalytics().query(siteUrl=site_url, body={**common, "rowLimit": 1}).execute()
        pages = svc.searchanalytics().query(siteUrl=site_url, body={**common, "dimensions": ["page"]}).execute()
        queries = svc.searchanalytics().query(siteUrl=site_url, body={**common, "dimensions": ["query"]}).execute()
        return totals, pages, queries, start.isoformat(), end.isoformat()

    try:
        totals, pages, queries, sd, ed = await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "403" in msg or "PERMISSION_DENIED" in msg:
            raise HTTPException(403,
                f"Service account lacks access to {site_url}. "
                "Adaugă email-ul SA în Search Console → Settings → Users.")
        if "404" in msg or "NOT_FOUND" in msg:
            raise HTTPException(404, f"Site {site_url} not found in Search Console.")
        raise HTTPException(500, f"GSC query failed: {msg[:300]}")

    def _agg(row):
        return {
            "clicks": int(row.get("clicks", 0) or 0),
            "impressions": int(row.get("impressions", 0) or 0),
            "ctr": float(row.get("ctr", 0) or 0),
            "position": float(row.get("position", 0) or 0),
        }

    totals_row = (totals.get("rows") or [{}])[0]
    top_pages = [{"page": (r.get("keys") or [""])[0], **_agg(r)} for r in (pages.get("rows") or [])]
    top_queries = [{"query": (r.get("keys") or [""])[0], **_agg(r)} for r in (queries.get("rows") or [])]

    # Find "zombie" pages — videos in our DB whose URL got 0 impressions.
    indexed_pages = {p["page"] for p in top_pages if p["impressions"] > 0}
    base = site_url.rstrip("/")
    zombies: list[dict] = []
    cur = db.videos.find(
        {"status": "ready"},
        {"_id": 0, "id": 1, "slug": 1, "title": 1, "created_at": 1},
    ).sort("created_at", -1).limit(500)
    async for v in cur:
        url = f"{base}/watch/{v.get('slug') or v['id']}"
        if url not in indexed_pages:
            zombies.append({
                "url": url,
                "title": v.get("title"),
                "video_id": v["id"],
                "slug": v.get("slug"),
                "created_at": v.get("created_at"),
            })

    return {
        "site_url": site_url,
        "start_date": sd,
        "end_date": ed,
        "days": days,
        "totals": _agg(totals_row),
        "top_pages": top_pages,
        "top_queries": top_queries,
        "zombies": zombies[:100],
        "zombie_count": len(zombies),
        "indexed_count": len(indexed_pages),
    }


# ============ SEO: Google Indexing API (request re-crawl) ============
@api.post("/admin/seo/request-indexing")
async def admin_seo_request_indexing(payload: dict, admin: dict = Depends(require_admin)):
    """Ping Google Indexing API to request (re)crawling for one or more URLs.

    Note: The Indexing API is *officially* limited to JobPosting and
    BroadcastEvent pages, but in practice Google still processes the request
    for arbitrary URLs and often triggers a Googlebot visit within hours.
    Daily quota is ~200 URL notifications per project.
    """
    urls = payload.get("urls") or []
    if not isinstance(urls, list) or not urls:
        raise HTTPException(400, "`urls` must be a non-empty list.")
    urls = [str(u).strip() for u in urls if str(u).strip()][:50]  # safety cap per call
    if not urls:
        raise HTTPException(400, "No valid URLs provided.")

    s = await get_settings()
    sa_raw = s.get("gsc_service_account_json") or ""
    if not sa_raw:
        raise HTTPException(400, "Google Search Console credentials not configured.")
    try:
        sa = json.loads(sa_raw)
    except Exception:
        raise HTTPException(500, "Stored GSC credentials are corrupt; please re-upload.")

    def _publish(url: str) -> dict:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        creds = service_account.Credentials.from_service_account_info(
            sa, scopes=["https://www.googleapis.com/auth/indexing"],
        )
        svc = build("indexing", "v3", credentials=creds, cache_discovery=False)
        try:
            resp = svc.urlNotifications().publish(
                body={"url": url, "type": "URL_UPDATED"}
            ).execute()
            return {"url": url, "ok": True, "notify_time": (resp.get("urlNotificationMetadata", {}).get("latestUpdate", {}) or {}).get("notifyTime")}
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            msg = (e.content or b"").decode("utf-8", "replace") if hasattr(e, "content") else str(e)
            return {"url": url, "ok": False, "status": status, "error": msg[:300]}
        except Exception as e:  # noqa: BLE001
            return {"url": url, "ok": False, "error": str(e)[:300]}

    def _run_all():
        return [_publish(u) for u in urls]

    results = await asyncio.to_thread(_run_all)
    ok_count = sum(1 for r in results if r.get("ok"))
    return {"ok": ok_count == len(results), "submitted": len(results), "success": ok_count, "results": results}


# ============ AI Synopsis generation (Emergent LLM key) ============

async def _consume_synopsis_quota(count: int) -> int:
    """Atomically increment the daily counter and return remaining quota.

    Auto-resets `ai_synopsis_used_today` when the ISO date rolls over.
    Raises HTTP 429 if `count` would exceed `ai_synopsis_daily_limit`.
    Returns the new `used_today` value on success.
    """
    from datetime import datetime as _dt, timezone as _tz
    today = _dt.now(_tz.utc).strftime("%Y-%m-%d")
    s = await get_settings()
    limit = int(s.get("ai_synopsis_daily_limit", 50))
    used = int(s.get("ai_synopsis_used_today", 0))
    reset_date = s.get("ai_synopsis_reset_date") or ""
    if reset_date != today:
        used = 0
        reset_date = today
    if used + count > limit:
        raise HTTPException(429, f"AI synopsis daily limit reached ({used}/{limit}). Increase in Admin → Settings → AI Synopsis or wait until tomorrow.")
    new_used = used + count
    await db.settings.update_one(
        {"_id": "app"},
        {"$set": {"ai_synopsis_used_today": new_used, "ai_synopsis_reset_date": today}},
        upsert=True,
    )
    return new_used


def _synopsis_prompt(video: dict, category_name: str = "") -> str:
    """Build the LLM prompt for generating one video's synopsis in Romanian."""
    title = (video.get("title") or "").strip() or "Episod anime"
    desc = (video.get("description") or "").strip()
    tags = ", ".join(video.get("tags") or [])
    parts = [f"Titlu episod: {title}"]
    if category_name:
        parts.append(f"Categorie: {category_name}")
    if tags:
        parts.append(f"Tag-uri: {tags}")
    if desc:
        parts.append(f"Descriere existentă: {desc[:400]}")
    parts.append(
        "\nGenerează un sinopsis unic de 180-220 cuvinte în limba română despre acest episod, "
        "menit pentru SEO Google. Cerințe:\n"
        "- Text natural, atrăgător pentru cititori\n"
        "- Menționează personajele și temele probabile bazate pe titlu/tag-uri\n"
        "- NU repeta descrierea existentă cuvânt-cu-cuvânt\n"
        "- NU folosi structuri repetitive ('În acest episod', 'Vei vedea')\n"
        "- Include cuvinte-cheie SEO relevante natural în text\n"
        "- Un singur paragraf, fără liste, fără titluri\n"
        "- Răspunde DOAR cu sinopsis-ul, fără introduceri sau ghilimele"
    )
    return "\n".join(parts)


async def _generate_synopsis_llm(video: dict, model: str, category_name: str = "") -> str:
    """Call the LLM to generate one synopsis.  Returns the raw text."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    # Prefer the key stored in DB settings (managed via Admin UI); fall back
    # to the EMERGENT_LLM_KEY environment variable for backwards compat.
    s = await get_settings()
    api_key = (s.get("emergent_llm_key") or "").strip() or os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            500,
            "Emergent LLM Key not configured. Go to Admin → Settings → ✨ AI Synopsis and paste your key.",
        )
    provider = "anthropic" if model.startswith("claude") else ("gemini" if model.startswith("gemini") else "openai")
    chat = LlmChat(
        api_key=api_key,
        session_id=f"synopsis-{video['id']}",
        system_message="You are a professional SEO copywriter fluent in Romanian, specialized in anime/streaming content.",
    ).with_model(provider, model)
    prompt = _synopsis_prompt(video, category_name)
    result = await chat.send_message(UserMessage(text=prompt))
    if isinstance(result, str):
        return result.strip()
    # emergentintegrations may return an object with .content
    return str(result).strip()


@api.post("/admin/videos/{video_id}/generate-synopsis")
async def admin_generate_synopsis_single(
    video_id: str,
    payload: dict | None = None,
    admin: dict = Depends(require_admin),
):
    """Generate a synopsis for a single video WITHOUT saving it.

    Admin gets a preview and can accept/reject before saving via the normal
    PATCH /api/videos/:id endpoint.
    """
    payload = payload or {}
    v = await find_video_by_id_or_slug(video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    s = await get_settings()
    if not s.get("ai_synopsis_enabled", True):
        raise HTTPException(403, "AI synopsis is disabled by admin settings.")
    await _consume_synopsis_quota(1)
    model = (payload.get("model") or s.get("ai_synopsis_model") or "claude-haiku-4-5-20251001").strip()
    # Fetch category label for richer prompts
    cat_name = ""
    if v.get("category_id"):
        cat = await db.categories.find_one({"id": v["category_id"]}, {"_id": 0, "name": 1})
        cat_name = (cat or {}).get("name", "")
    try:
        text = await _generate_synopsis_llm(v, model, cat_name)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"LLM call failed: {str(e)[:200]}")
    word_count = len([w for w in text.split() if w])
    return {"synopsis": text, "word_count": word_count, "model": model, "video_id": v["id"]}


@api.post("/admin/videos/generate-synopsis-bulk")
async def admin_generate_synopsis_bulk(
    payload: dict,
    admin: dict = Depends(require_admin),
):
    """Generate + save synopsis for many videos at once.

    Body: {"video_ids": ["id1", "id2", ...], "model": "..." (optional),
           "skip_existing": true (default) — don't overwrite videos that
           already have a non-empty synopsis}
    Returns per-video result with ok/error + generated text.
    """
    ids = payload.get("video_ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "`video_ids` must be a non-empty list.")
    ids = [str(i) for i in ids][:100]  # safety cap per request
    s = await get_settings()
    if not s.get("ai_synopsis_enabled", True):
        raise HTTPException(403, "AI synopsis is disabled.")
    model = (payload.get("model") or s.get("ai_synopsis_model") or "claude-haiku-4-5-20251001").strip()
    skip_existing = payload.get("skip_existing", True)

    # Load all requested videos + categories in one round-trip
    vids = await db.videos.find({"id": {"$in": ids}}, {"_id": 0}).to_list(len(ids))
    cats = await db.categories.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
    cat_map = {c["id"]: c.get("name", "") for c in cats}

    # Filter out videos that already have a synopsis
    to_generate = [v for v in vids if not (skip_existing and (v.get("synopsis") or "").strip())]
    if not to_generate:
        return {"ok": True, "submitted": 0, "success": 0, "skipped": len(vids), "results": []}

    # Reserve quota upfront so we fail fast
    await _consume_synopsis_quota(len(to_generate))

    results: list[dict] = []
    for v in to_generate:
        try:
            text = await _generate_synopsis_llm(v, model, cat_map.get(v.get("category_id") or "", ""))
            await db.videos.update_one({"id": v["id"]}, {"$set": {"synopsis": text}})
            results.append({"video_id": v["id"], "ok": True, "words": len(text.split())})
        except Exception as e:  # noqa: BLE001
            results.append({"video_id": v["id"], "ok": False, "error": str(e)[:200]})

    ok_count = sum(1 for r in results if r["ok"])
    return {
        "ok": ok_count == len(results),
        "submitted": len(to_generate),
        "success": ok_count,
        "skipped": len(vids) - len(to_generate),
        "results": results,
    }


@api.get("/admin/videos/synopsis-quota")
async def admin_synopsis_quota(admin: dict = Depends(require_admin)):
    """Return current daily quota status for the AI Synopsis feature."""
    from datetime import datetime as _dt, timezone as _tz
    today = _dt.now(_tz.utc).strftime("%Y-%m-%d")
    s = await get_settings()
    used = int(s.get("ai_synopsis_used_today", 0))
    reset_date = s.get("ai_synopsis_reset_date") or ""
    if reset_date != today:
        used = 0
    limit = int(s.get("ai_synopsis_daily_limit", 50))
    return {
        "used_today": used,
        "daily_limit": limit,
        "remaining": max(0, limit - used),
        "model": s.get("ai_synopsis_model") or "claude-haiku-4-5-20251001",
        "enabled": bool(s.get("ai_synopsis_enabled", True)),
    }


# ============ SEO: robots.txt + sitemap.xml (mounted at app root) ============
@app.api_route("/robots.txt", methods=["GET", "HEAD"], include_in_schema=False)
async def robots_txt():
    """Tell search engines which paths are crawlable + where the sitemap is.

    Disallow `/api/` and admin / internal paths so Googlebot doesn't waste
    its crawl budget on JSON endpoints.
    """
    s = await get_settings()
    base = (s.get("site_canonical_url") or "").rstrip("/")
    sitemap_loc = f"{base}/sitemap.xml" if base else "/sitemap.xml"
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /admin\n"
        "Disallow: /edit-video/\n"
        "Disallow: /upload\n"
        "Disallow: /login\n"
        "Disallow: /register\n"
        "Disallow: /shop\n"
        f"Sitemap: {sitemap_loc}\n"
    )
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(body, headers={"Cache-Control": "public, max-age=3600"})


@app.api_route("/sitemap.xml", methods=["GET", "HEAD"], include_in_schema=False)
async def sitemap_xml(request: Request):
    """XML sitemap listing the homepage, every category, and every public video.

    Submitted to Google Search Console at:
      https://search.google.com/search-console
    """
    from fastapi.responses import Response as _XMLResponse
    import html as _html
    esc = _html.escape
    s = await get_settings()
    base = (s.get("site_canonical_url") or "").rstrip("/")
    if not base:
        # Fall back to whatever scheme+host the request came in on so the
        # XML works even when the admin hasn't configured a canonical URL.
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        host = request.headers.get("host") or request.url.hostname or ""
        if host:
            base = f"{proto}://{host}"

    urls: list[str] = []

    def add(loc: str, lastmod: str = "", priority: str = "0.5", changefreq: str = "weekly") -> None:
        u = f"  <url>\n    <loc>{esc(base + loc) if loc.startswith('/') else esc(loc)}</loc>\n"
        if lastmod:
            u += f"    <lastmod>{esc(lastmod[:10])}</lastmod>\n"
        u += f"    <changefreq>{changefreq}</changefreq>\n    <priority>{priority}</priority>\n  </url>"
        urls.append(u)

    add("/", priority="1.0", changefreq="daily")
    add("/popular", priority="0.7", changefreq="daily")
    add("/discover", priority="0.7", changefreq="daily")
    add("/shorts", priority="0.7", changefreq="daily")
    add("/all-episodes", priority="0.7", changefreq="daily")

    try:
        cats = await db.categories.find({}, {"_id": 0, "slug": 1}).to_list(500)
        for c in cats:
            add(f"/category/{c['slug']}", priority="0.6", changefreq="weekly")
    except Exception:
        pass

    try:
        # Cap at 5000 — Google's sitemap limit is 50k but most VPS DBs are
        # smaller and a single XML response should stay under 50MB anyway.
        cur = db.videos.find(
            {"status": "ready"},
            {"_id": 0, "id": 1, "slug": 1, "title": 1, "thumbnail_url": 1, "created_at": 1, "updated_at": 1},
        ).sort("created_at", -1).limit(5000)
        async for v in cur:
            slug_or_id = v.get("slug") or v["id"]
            add(
                f"/watch/{slug_or_id}",
                lastmod=str(v.get("updated_at") or v.get("created_at") or ""),
                priority="0.8",
                changefreq="monthly",
            )
    except Exception:
        pass

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    return _XMLResponse(
        content=xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


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
    # Resolve slug→uuid so subscribers using SEO URLs receive updates.
    vid = await resolve_video_id(video_id) or video_id
    cid = await video_status_hub.connect(vid, websocket)
    try:
        # Send an initial snapshot so the UI doesn't need a separate fetch.
        snap = await db.videos.find_one(
            {"id": vid},
            {"_id": 0, "status": 1, "progress": 1, "renditions": 1, "error": 1,
             "thumbnail_url": 1, "is_short": 1, "duration_sec": 1},
        )
        if snap:
            import json as _json
            await websocket.send_text(_json.dumps(
                {"type": "video.status", "video_id": vid, "data": snap}, default=str,
            ))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.debug("video.status ws closed: %s", e)
    finally:
        await video_status_hub.disconnect(vid, cid)


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


# ============ Crawler-aware /watch/<id> safety net ============
# Belt-and-suspenders: even if nginx isn't configured to redirect social-media
# crawlers to /api/og/video/<id>, this middleware catches them too.  Humans
# (no matching UA) fall through to the SPA via Starlette/Uvicorn unchanged.
_SOCIAL_CRAWLER_RE = re.compile(
    r"(facebookexternalhit|facebot|twitterbot|discordbot|slackbot|"
    r"telegrambot|whatsapp|linkedinbot|googlebot|bingbot|embedly|"
    r"pinterest|redditbot|mastodon|iframely|skypeuripreview|applebot|yahoo|"
    r"vkshare|w3c_validator|baiduspider|ia_archiver)",
    re.IGNORECASE,
)
_WATCH_PATH_RE = re.compile(r"^/watch/([^/?#]+)")
_CATEGORY_PATH_RE = re.compile(r"^/(?:videos/)?category/([^/?#]+)")
_LISTING_PATH_RE = re.compile(r"^/(popular|discover|shorts|all-episodes|episoade|shop)(?:/|$)")

# Legacy URL recovery: any `.html` URL at the app root MAY have been an
# article slug from the previous CMS.  We try to resolve it via
# `find_video_by_id_or_slug` and 301-redirect to the canonical `/watch/<slug>`.
_LEGACY_HTML_RE = re.compile(r"^/([^/?#]+\.html)$", re.IGNORECASE)


@app.middleware("http")
async def crawler_og_middleware(request: Request, call_next):
    """Crawler-aware OG SSR + legacy `.html` URL redirector.

    Two responsibilities:
      1. For known social-media crawlers hitting /watch/<id> or /,
         return server-rendered HTML with proper OG tags.
      2. For ANY visitor (human or bot) hitting a legacy `*.html` URL
         that was indexed before the migration, issue a HTTP 301 redirect
         to the canonical `/watch/<slug>` so old links + Google's cached
         results still resolve.  Recovers historic SEO authority.

    Non-matching requests flow straight through to the SPA / regular routes.
    """
    path = request.url.path or "/"

    # ── 1) Legacy *.html → /watch/<slug> 301 redirect ───────────────────
    legacy_match = _LEGACY_HTML_RE.match(path)
    if legacy_match:
        legacy_name = legacy_match.group(1)  # "title_xxxx.html"
        try:
            from fastapi.responses import RedirectResponse
            # Try a few resolution strategies:
            #   - exact legacy_slug match (with or without .html suffix)
            #   - bare stem match (drop the .html)
            stem = legacy_name[:-5]
            v = None
            for key in (legacy_name, stem):
                v = await find_video_by_id_or_slug(key)
                if v:
                    break
            # Last-ditch: pattern `<slug>_<rand>.html` — pull off the `_<rand>` part
            if v is None and "_" in stem:
                v = await find_video_by_id_or_slug(stem.rsplit("_", 1)[0])
            if v:
                # 301 = permanent → Google transfers the SEO authority from
                # the old URL to the new one.
                target = f"/watch/{v.get('slug') or v['id']}"
                return RedirectResponse(target, status_code=301)
        except Exception as e:  # noqa: BLE001
            logger.warning("legacy html redirect lookup failed for %s: %s", path, e)

    # ── 2) Crawler OG SSR ───────────────────────────────────────────────
    ua = request.headers.get("user-agent", "")
    if ua and _SOCIAL_CRAWLER_RE.search(ua):
        m = _WATCH_PATH_RE.match(path)
        if m:
            return await og_video_html(m.group(1), request)  # type: ignore[arg-type]
        cm = _CATEGORY_PATH_RE.match(path)
        if cm:
            return await og_category_html(cm.group(1), request)  # type: ignore[arg-type]
        if _LISTING_PATH_RE.match(path):
            return await og_home_html()  # type: ignore[call-arg]
        if path == "/" or path == "":
            return await og_home_html()  # type: ignore[call-arg]
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
