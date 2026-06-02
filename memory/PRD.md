# StreamHub — Product Requirements & Status

## Original problem statement
Build a full-stack video-sharing platform inspired by hentairosub.ro with:
- Pro/Free video access tiers
- FFmpeg auto-transcoding (360p → 4096p) + 10 thumbnail extraction per upload
- Wasabi S3 + CloudFront signed URLs for Pro protection
- Stripe-based PRO subscription packages
- Admin panel (videos, users, categories, packages, announcements, settings, chat moderation)
- Live chat for the community
- Romanian/English UI
- Legacy SQL → MongoDB migration tool
- One-command VPS docker-compose deployment

## Tech stack
- **Frontend**: React 19, TailwindCSS, Shadcn/UI, Lucide icons, Sonner toasts, native WebSocket
- **Backend**: FastAPI, Motor (async MongoDB), bcrypt, jose JWT, boto3 (Wasabi/S3), Stripe SDK
- **Transcoder**: FFmpeg via async subprocess pool
- **Deployment**: docker-compose (mongo + backend + frontend + nginx + certbot)

## What's implemented (Feb 2026)
- ✅ Email/password auth + JWT + email verification + brute-force lockout
- ✅ Upload with FFmpeg transcoding pipeline (background, progressive — status flips to "ready" on first rendition done)
- ✅ Pro tier with Wasabi S3 storage + signed URLs (S3 presign OR CloudFront key-pair)
- ✅ Stripe checkout for packages
- ✅ Admin panel: dashboard, videos (Edit + delete), users (ban/unban/grant-pro/role), categories, packages, announcements, live-chat moderation, settings (Localization, Shorts, Live Chat, Legacy migration, FFmpeg, Storage, SMTP, Stripe, Signed URLs, CloudFront, Contact, SEO, Auth security, GitHub auto-update)
- ✅ Profile (avatar, cover, owned videos, inline Edit/Delete)
- ✅ Custom HTML5 video player with resolution selector, CC, download toggle
- ✅ **Mobile responsive layout** with hamburger drawer
- ✅ **Live Chat** via native FastAPI WebSocket, with per-message rate-limiting, guest support, admin ban/delete moderation, chat_banned_until separate from site ban
- ✅ **RO/EN bilingual UI** with admin-configurable default + per-visitor override (LanguageContext + i18n.js)
- ✅ **Shorts**: auto-detected (vertical + duration ≤ configurable max) + manual toggle on upload, dedicated /shorts route + vertical grid + Home "Last Shorts added" section
- ✅ **Homepage**: 12 videos per section + "See more" buttons + new hero text "Vezi hentai subtitrat în limba română la calitate 1080P - 4096P"
- ✅ **Legacy migration tool**: `--all-pro` flag forces imported catalogue to PRO; vertical-aspect short auto-detection
- ✅ **Pagination** ("Load more") on Category, Popular, Discover, Shorts, All-Episodes pages
- ✅ Site config (title, favicon, SEO meta) stored in DB and editable from Admin → Settings
- ✅ Secrets (JWT, Stripe, SMTP, Wasabi, CloudFront) moved from .env to MongoDB site_config
- ✅ One-command VPS installer (`/app/deploy/scripts/install.sh`) with self-diagnostic + bundle collector
- ✅ Auto-update via Admin → Settings → GitHub
- ✅ Watch page processing overlay with status polling

## Roadmap / Future improvements
- P2 — Subtitles upload flow in EditVideo page (model fields exist, UI partial)
- P2 — Multi-language metadata (currently `description` is a single string)
- P2 — Per-user playlist / favourites
- P2 — Notification system (in-app bell for new messages, replies, video ready)
- P3 — Refactor `server.py` (currently 1700 lines) into `routes/auth.py`, `routes/videos.py`, `routes/admin.py`, `routes/chat.py`, `routes/billing.py`. Add `models/` package. Move chat/storage helpers under `/app/backend/services/`.
- P3 — Replace polling on Watch page with WebSocket "video.status" channel
- P3 — Migration tool: backfill `is_short` from existing thumbnails by inspecting actual rendition dimensions

## Test data
- Admin: `admin@streamhub.io` / `Admin123!`
- Owner: `owner@streamhub.io` / `Owner@2026!`
- Tests: see `/app/backend/tests/test_iteration4.py`; report at `/app/test_reports/iteration_4.json` (15/15 backend + 16/16 frontend = 100% pass).

## Deployment
- See `/app/deploy/README.md` then `sudo bash /app/deploy/scripts/install.sh`.
- Migration: `python3 deploy/migrate/parse_legacy_dump.py --sql dump.sql --out-dir ./out --all-pro --wasabi-base-url …` then `bash deploy/migrate/import_to_mongo.sh`.
