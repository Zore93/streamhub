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
- ✅ Mobile responsive layout with hamburger drawer
- ✅ Live Chat via native FastAPI WebSocket
- ✅ RO/EN bilingual UI with admin-configurable default + per-visitor override
- ✅ Shorts (vertical + duration auto-detect + manual toggle), dedicated /shorts route, Home "Last Shorts added" section
- ✅ Homepage: 12 videos per section + "See more" buttons + new hero text positioned lower
- ✅ Legacy migration tool: `--all-pro` + `--shorts-max-seconds` flags
- ✅ Pagination ("Load more") on Category + Popular + Discover + Shorts + All-Episodes
- ✅ Site config (title, favicon, SEO meta) stored in DB
- ✅ Secrets (JWT, Stripe, SMTP, Wasabi, CloudFront) in MongoDB site_config
- ✅ One-command VPS installer + self-diagnostic + bundle collector
- ✅ Auto-update via Admin → Settings → GitHub (fixed Feb 2026): rich diagnostics, Configure/Change/Unset remote buttons, dubious-ownership safe.directory workaround, surfaced git stderr
- ✅ Watch page: WebSocket /api/videos/{id}/status push channel replaces 4-second polling (saves bandwidth + battery)
- ✅ EditVideo subtitles: language Select with 14 common locales + "Other" custom code, "Make default" reorder via PATCH, is_short toggle, srt/ass auto-conversion to WebVTT

## Roadmap / Future improvements
- P2 — Multi-language metadata (currently `description` is single string)
- P2 — Per-user playlists / favourites
- P3 — Refactor `server.py` (now ~1860 lines) into `routes/` package
- P3 — Notification system (in-app bell for video ready / replies)
- P3 — `git ls-remote` validation in /admin/github/set-remote for connectivity check
- P3 — Refactor models.py into `models/` package; move chat/storage helpers to `services/`

## Test data
- Admin: `admin@streamhub.io` / `Admin123!`
- Owner: `owner@streamhub.io` / `Owner@2026!`
- Tests: see `/app/backend/tests/test_iteration4.py`; report at `/app/test_reports/iteration_4.json` (15/15 backend + 16/16 frontend = 100% pass).

## Deployment
- See `/app/deploy/README.md` then `sudo bash /app/deploy/scripts/install.sh`.
- Migration: `python3 deploy/migrate/parse_legacy_dump.py --sql dump.sql --out-dir ./out --all-pro --wasabi-base-url …` then `bash deploy/migrate/import_to_mongo.sh`.
