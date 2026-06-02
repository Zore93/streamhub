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
    created_at: str = Field(default_factory=now_iso)


class UserPublic(BaseModel):
    id: str
    email: str
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
    created_at: str


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


# ============ COMMENT ============
class Comment(BaseModel):
    id: str = Field(default_factory=new_id)
    video_id: str
    user_id: str
    username: str
    avatar_url: Optional[str] = None
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
    smtp_use_tls: bool = True
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
    # Site / SEO
    site_title: str = "StreamHub"
    site_description: str = "A premium video-sharing community."
    site_favicon_url: str = ""
    site_seo_keywords: str = ""
    site_seo_meta: str = ""  # raw additional <meta> tags
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


# ============ ADMIN UPLOAD-PERMISSION CHECK ============
class StatsResponse(BaseModel):
    total_videos: int
    total_users: int
    total_views: int
    total_pro_users: int
    total_likes: int
    total_comments: int
