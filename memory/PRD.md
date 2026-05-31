# StreamHub — Product Requirements Document

## Original Problem
A video-sharing website similar to hentairosub.ro where users register, upload videos, and StreamHub auto-transcodes them with FFmpeg into multiple resolutions (360p/720p/1080p/2048p/4096p) with auto-generated thumbnails. Includes Pro paywall, Stripe payments, admin panel with full configuration, comments, likes, views, ban system, SMTP email verification, announcements, Wasabi S3 / Local storage toggle, and GitHub auto-update.

## Architecture
- **Backend**: FastAPI + MongoDB (motor). Background FFmpeg jobs via asyncio.Semaphore (admin-configurable concurrency). Storage on local disk under `/app/uploads/{originals,videos,thumbnails,avatars,covers}`. Stripe via `emergentintegrations`.
- **Frontend**: React + Tailwind + Shadcn UI. 3-column layout (Left categories sidebar, Main content, Right user/Pro/recommendations sidebar). Outfit (heading) + Manrope (body) fonts. Dark theme with rose→orange Pro gradient.
- **Auth**: JWT (bcrypt) with optional SMTP email verification (admin toggle).

## Implemented (Feb 2026)
- ✅ Register / Login / JWT auth, optional SMTP email verification
- ✅ Video upload (configurable max MB) + background FFmpeg transcode into enabled resolutions + 10 auto-thumbnails
- ✅ Home page with Latest (10) / Popular (10) / Random (10) sections
- ✅ Left sidebar: dynamic categories + navigation on every page
- ✅ Right sidebar: user profile mini-card or auth CTAs, Pro upgrade banner, package list. On Watch page, 15 recommendations.
- ✅ Video Watch page: HTML5 player, resolution picker (sources per rendition), comments, likes, views, locked overlay for Pro content
- ✅ User Profile: avatar + cover upload, uploaded-videos grid, self-delete videos
- ✅ Pro page with Stripe Checkout (uses STRIPE_API_KEY from env, admin can override), polling for status, pro_expires_at handling
- ✅ Admin Panel tabs: Dashboard (6 stats), Videos, Users (ban 1d/1w/1m/permanent/custom + role toggle), Categories CRUD, Packages CRUD (max 10), Announcements CRUD, Settings (FFmpeg, storage, SMTP, Stripe, GitHub, Wasabi)
- ✅ Announcement modal centered, dismissible (persisted in localStorage)
- ✅ GitHub `git pull` endpoint (admin-only)
- ✅ Wasabi S3 configuration UI in admin (boto3 available; actual S3 upload integration deferred)

## Test Results (iteration 1)
- Backend: **25/25 passing (100%)** — auth, FFmpeg transcode E2E (status=ready + 10 thumbnails + 2 renditions in ~10s), Stripe checkout session creation, all admin CRUD, ban/unban, email verification toggle.

## Backlog / P1
- Wasabi S3 actual upload pipeline (config UI exists)
- Typed Pydantic models for category/package/announcement create payloads
- Rate-limit `POST /api/videos/{id}/view` to prevent inflation
- Safeguard against last admin demoting themselves
- File-type validation on avatar/cover uploads

## P2 / Nice-to-have
- Watch history, playlists
- Subscription / follow uploader
- Search bar
- Email verification template HTML
- Real-time view counter

## Test Credentials
See `/app/memory/test_credentials.md`. Admin: `admin@streamhub.io` / `Admin123!`.
