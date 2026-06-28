"""Pydantic models for StreamHub."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import uuid
from pydantic import BaseModel, Field, EmailStr


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ============ USER ============
class User(BaseModel):
    id: str = Field(default_factory=new_id)
    email: EmailStr
    username: str
    password_hash: str
    role: str = "user"  # user | admin
    is_pro: bool = False
    pro_package_id: Optional[str] = None
    pro_expires_at: Optional[str] = None
    email_verified: bool = False
    verify_token: Optional[str] = None
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = None
    banned_until: Optional[str] = None  # ISO; "permanent" for permanent ban
    banned_reason: Optional[str] = None
    # Chat-specific ban (doesn't block site access — only chat sending)
    chat_banned_until: Optional[str] = None
    chat_banned_reason: Optional[str] = None
    # Coin economy
    coins: int = 0
    # Frames inventory
    owned_frames: List[str] = []  # AvatarFrame ids
    selected_frame_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class UserPublic(BaseModel):
    id: str
    username: str
    role: str
    is_pro: bool
    pro_package_id: Optional[str] = None
    pro_expires_at: Optional[str] = None
    email_verified: bool
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = None
    banned_until: Optional[str] = None
    coins: int = 0
    selected_frame_id: Optional[str] = None
    owned_frames: List[str] = []
    created_at: str
    # Email only included for self/admin views (added dynamically by server)
    email: Optional[str] = None


class RegisterReq(BaseModel):
    email: EmailStr
    username: str
    password: str


class LoginReq(BaseModel):
    email: EmailStr
    password: str


# ============ CATEGORY ============
class Category(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    slug: str
    created_at: str = Field(default_factory=now_iso)


# ============ VIDEO ============
class VideoRendition(BaseModel):
    resolution: str  # "360p", "720p", etc.
    url: str
    width: int = 0
    height: int = 0


class Subtitle(BaseModel):
    id: str = Field(default_factory=new_id)
    language: str  # e.g. "en", "ro"
    label: str  # display name e.g. "English"
    url: str  # WebVTT URL (for playback)
    original_url: Optional[str] = None  # original .srt/.ass
    format: str = "vtt"  # vtt | srt | ass
    created_at: str = Field(default_factory=now_iso)


class Video(BaseModel):
    id: str = Field(default_factory=new_id)
    title: str
    slug: Optional[str] = None  # SEO-friendly URL slug (unique)
    description: str = ""
    tags: List[str] = []
    category_id: Optional[str] = None
    uploader_id: str
    uploader_username: str = ""
    thumbnail_url: Optional[str] = None
    thumbnail_options: List[str] = []  # all generated thumbs
    duration_sec: float = 0.0
    original_filename: str = ""
    original_size_bytes: int = 0
    original_width: int = 0
    original_height: int = 0
    status: str = "processing"  # processing | ready | failed
    progress: int = 0
    error: Optional[str] = None
    renditions: List[VideoRendition] = []
    subtitles: List[Subtitle] = []
    access_tier: str = "free"  # free | pro
    is_short: bool = False  # True for vertical / short-form clips
    views: int = 0
    likes: List[str] = []  # user ids
    created_at: str = Field(default_factory=now_iso)


class VideoUploadMeta(BaseModel):
    title: str
    description: str = ""
    tags: List[str] = []
    category_id: Optional[str] = None
    access_tier: str = "free"
    thumbnail_index: int = 0


class VideoUpdateReq(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    category_id: Optional[str] = None
    access_tier: Optional[str] = None
    thumbnail_url: Optional[str] = None
    is_short: Optional[bool] = None
    subtitles: Optional[List[dict]] = None  # allow reordering (set default) only — items must already exist


# ============ COMMENT ============
class Comment(BaseModel):
    id: str = Field(default_factory=new_id)
    video_id: str
    user_id: str
    username: str
    avatar_url: Optional[str] = None
    frame_id: Optional[str] = None  # snapshot of selected_frame_id at write time
    content: str
    created_at: str = Field(default_factory=now_iso)


class CommentReq(BaseModel):
    content: str


# ============ PACKAGE ============
class Package(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    description: str = ""
    color: str = "#f43f5e"
    price: float = 0.0
    currency: str = "usd"
    duration_days: int = 30
    active: bool = True
    sort_order: int = 0
    created_at: str = Field(default_factory=now_iso)


# ============ ANNOUNCEMENT ============
class Announcement(BaseModel):
    id: str = Field(default_factory=new_id)
    title: str
    content: str
    active: bool = True
    created_at: str = Field(default_factory=now_iso)


# ============ SETTINGS ============
class AppSettings(BaseModel):
    # FFmpeg
    ffmpeg_concurrency: int = 2
    enabled_resolutions: List[str] = ["360p", "720p", "1080p"]
    # Upload
    max_upload_size_mb: int = 1024
    allow_user_uploads: bool = True
    bulk_upload_enabled: bool = True  # admin can disable multi-file upload UI
    bulk_upload_concurrency: int = 3  # how many chunks/files to send in parallel
    chunk_upload_chunk_size_mb: int = 25  # client target chunk size
    # Storage
    storage_backend: str = "local"  # local | wasabi
    wasabi_access_key: str = ""
    wasabi_secret_key: str = ""
    wasabi_bucket: str = ""
    wasabi_region: str = "us-east-1"
    wasabi_endpoint: str = "https://s3.wasabisys.com"
    wasabi_public_base_url: str = ""
    # SMTP
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True  # legacy boolean — kept for backwards compat
    smtp_security: str = ""    # "" (auto) | "starttls" | "ssl" | "none"
    require_email_verification: bool = False
    # Stripe
    stripe_secret_key: str = ""  # if blank, uses env STRIPE_API_KEY
    stripe_publishable_key: str = ""
    # Signed URLs (Pro content protection)
    signed_url_ttl_seconds: int = 300
    # CloudFront signed URLs (optional - takes precedence over S3 presign when enabled)
    cloudfront_enabled: bool = False
    cloudfront_domain: str = ""  # e.g. d123.cloudfront.net  (no protocol)
    cloudfront_key_pair_id: str = ""
    cloudfront_private_key: str = ""  # PEM body
    # Contact
    contact_email: str = ""
    # Player
    allow_video_download: bool = False
    # SEO / Google Search Console
    gsc_service_account_json: str = ""  # raw JSON of the service account key
    gsc_site_url: str = ""              # e.g. https://hentairosub.ro/
    # Site / SEO
    site_title: str = "StreamHub"
    site_description: str = "A premium video-sharing community."
    home_hero_text: str = ""  # custom tagline shown on /; falls back to i18n if empty
    site_favicon_url: str = ""
    site_logo_url: str = ""   # left-sidebar brand logo; replaces the "S" + name when set
    site_seo_keywords: str = ""
    site_seo_meta: str = ""
    site_og_image: str = ""   # default Open Graph image (used as fallback for embeds)
    site_canonical_url: str = ""  # canonical base URL e.g. https://gleague.eu (used for og:url + sharing)  # raw additional <meta> tags
    # Auth security
    min_password_length: int = 8
    require_password_complexity: bool = True
    login_rate_limit_max: int = 5     # attempts
    login_rate_limit_window: int = 300  # seconds
    # Bootstrapped secrets (auto-generated on first boot if blank; can be edited
    # from Admin → Settings instead of editing /opt/streamhub/deploy/.env)
    jwt_secret: str = ""
    # GitHub auto-update
    github_repo: str = ""
    github_token: str = ""
    github_branch: str = "main"
    # Localization
    default_language: str = "ro"  # ro | en
    # Shorts detection
    shorts_max_duration_sec: int = 60  # videos shorter than this AND vertical = Short
    # Live chat
    live_chat_enabled: bool = True
    live_chat_guest_allowed: bool = True
    live_chat_max_message_length: int = 500
    live_chat_rate_limit_seconds: int = 3
    # Legacy migration
    legacy_videos_pro_only: bool = True  # newly migrated legacy videos become PRO-only
    # Coin economy
    coins_per_like: int = 1
    coins_per_comment: int = 2
    coins_comment_daily_cap_per_video: int = 10  # max coin-rewarded comments / day / video


class SettingsUpdateReq(BaseModel):
    data: Dict[str, Any]


# ============ PAYMENT ============
class PaymentTransaction(BaseModel):
    id: str = Field(default_factory=new_id)
    session_id: str
    user_id: str
    user_email: str
    package_id: str
    amount: float
    currency: str
    payment_status: str = "pending"  # pending | paid | expired | failed
    status: str = "open"
    metadata: Dict[str, str] = {}
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


# ============ BAN ============
class BanReq(BaseModel):
    duration: str  # "1day" | "1week" | "1month" | "permanent" | "custom"
    custom_days: Optional[int] = None
    reason: Optional[str] = None


# ============ CHAT ============
class ChatMessage(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: Optional[str] = None  # None for guests
    guest_session: Optional[str] = None  # used for guest bans
    username: str
    avatar_url: Optional[str] = None
    is_pro: bool = False
    role: str = "guest"  # guest | user | admin
    content: str
    created_at: str = Field(default_factory=now_iso)


class ChatSendReq(BaseModel):
    content: str
    guest_session: Optional[str] = None  # required when not authed
    guest_name: Optional[str] = None  # required when not authed


class ChatBanReq(BaseModel):
    duration: str  # "1day" | "1week" | "1month" | "permanent" | "custom"
    custom_days: Optional[int] = None
    reason: Optional[str] = None


class GuestChatBan(BaseModel):
    id: str = Field(default_factory=new_id)
    guest_session: str
    banned_until: str  # ISO or "permanent"
    reason: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


# ============ ADMIN UPLOAD-PERMISSION CHECK ============
class StatsResponse(BaseModel):
    total_videos: int
    total_users: int
    total_views: int
    total_pro_users: int
    total_likes: int
    total_comments: int


# ============ AVATAR FRAMES (shop) ============
class AvatarFrame(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    # The "visual" of the frame is a CSS effect key. Listed in FRAME_EFFECT_KEYS
    # below; the React `<FramedAvatar>` component owns the actual animation CSS.
    effect_key: str = "neon-ring"
    # Color used by the effect (CSS color). Optional secondary color too.
    color_primary: str = "#f43f5e"
    color_secondary: str = "#fb7185"
    rarity: str = "common"  # common | rare | epic | legendary
    price_coins: int = 100
    active: bool = True
    sort_order: int = 0
    created_at: str = Field(default_factory=now_iso)


# Coin transaction (for audit / preventing double-credit on like)
class CoinTxn(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    delta: int  # positive earn / negative spend
    reason: str  # "like:<videoid>" | "comment:<videoid>" | "purchase:<frameid>"
    balance_after: int
    created_at: str = Field(default_factory=now_iso)
