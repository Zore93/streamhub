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
- ✅ Auto-update via Admin → Settings → GitHub (Feb 2026 v3):
   * Rich diagnostics (`errors[]` array surfaces git stderr instead of "?")
   * `safe.directory=*` bypasses dubious-ownership rejection in docker
   * **Dual-mode "Configure remote" form**: friendly Repo-URL+PAT (recommended) or raw URL
   * `POST /admin/github/set-remote-with-token` verifies the token via `git fetch` BEFORE saving (rolls back on failure)
   * Token NEVER leaves the server — UI shows scrubbed URL; PAT stored in settings.github_token
   * `DELETE /admin/github/remote` cleans both git config + DB settings
- ✅ **Legacy → Shorts bulk action** (Admin → Settings → Legacy migration):
   * `GET /admin/videos/legacy-stats` — total / as-Shorts / as-videos counts
   * `POST /admin/videos/mark-legacy-as-shorts` — flip `is_short=True` on every migrated doc
   * `POST /admin/videos/mark-legacy-as-videos` — reverse
- ✅ Watch page: WebSocket /api/videos/{id}/status push channel replaces 4-second polling (saves bandwidth + battery)
- ✅ EditVideo subtitles: language Select with 14 common locales + "Other" custom code, "Make default" reorder via PATCH, is_short toggle, srt/ass auto-conversion to WebVTT
- ✅ **SEO slug URLs (Feb 2026)** — videos served at `/watch/<slug>-<6char>` (e.g. `/watch/kutsujoku-sezonul-2-ep1-aB3xY7`). UUID URLs still work and 301-replace in the URL bar to the slug. Backfill script: `python -m scripts.backfill_video_slugs`.
- ✅ **SSR Open Graph for crawlers (Feb 2026)** — FastAPI middleware intercepts /watch/<id> requests from social-media crawlers (Facebook/Discord/Twitter/Telegram/Slack/etc) and returns server-rendered HTML with og:title, og:description and og:image (the actual video thumbnail). Production VPS nginx also has a `is_social_crawler` map that routes those UAs to /api/og/video/<id>.
- ✅ **Coin economy (Feb 2026)** — users earn coins per like (first-time only, idempotent via `coin_ledger`) and per comment (capped at N rewarded comments / day / video). Admin sets `coins_per_like`, `coins_per_comment`, `coins_comment_daily_cap_per_video` in Admin → Settings → Economie Monede.
- ✅ **Avatar frames + Shop (Feb 2026)** — 50 default CSS-animated avatar frames (28 unique `effect_key` animations × multiple color schemes; rarities common/rare/epic/legendary). Square avatars (`rounded-md`). New `/shop` page accessible from right-sidebar. Profile page has a "Cadre" tab for applying owned frames. Comment avatars are 100×100 with the user's currently selected frame. Admin Panel has a "Cadre Avatar" tab for CRUD + a `POST /admin/frames/seed` button.
- ✅ **Chunked / resumable uploads (Feb 2026)** — new endpoints `/api/videos/upload/init|chunk|status|finish|abort` bypass nginx body limits entirely. Frontend uploader (`/app/frontend/src/lib/chunkedUpload.js`) sends 25MB chunks (admin-configurable) with auto-retry + exponential backoff. Required for files >4GB on production VPS.
- ✅ **Bulk upload (Feb 2026)** — `Upload.jsx` lets users queue up to 50 files at once with per-file inline title editing + concurrent uploads (default 3 parallel, admin-configurable). Post-upload, each successful video shows an inline "Edit" + "Vizionează" link. Admin toggle: `bulk_upload_enabled`.
- ✅ **Configurable homepage hero text (Feb 2026)** — `AppSettings.home_hero_text`; Admin → Settings → "Home page hero text" textarea. Falls back to i18n translation when empty.
- ✅ **Subtitle language auto-detect (Feb 2026)** — `languages.py` ships a `detect_language_from_filename` that recognises 80+ patterns (e.g. `episode01.ja-jp.srt` → `ja`, `Romanian.srt` → `ro`, `epizod-rosub.srt` → `ro`). Server uses it whenever a subtitle is uploaded without an explicit `language` form field. Client (`EditVideo.jsx`) also runs a lightweight client-side detect and shows a green "Limbă detectată automat din nume fișier" hint.
- ✅ **Max 100 subtitles / video + 192 ISO 639 languages (Feb 2026)** — bumped from 10/14 to 100/192. New `GET /api/languages` endpoint feeds the EditVideo dropdown. `normalize_language_code` maps `ron`→`ro`, `jpn`→`ja`, etc. for embedded MKV subs.
- ✅ **Sticky settings save bar (Feb 2026)** — Admin → Settings shows a sticky bar at the top with "Modificări nesalvate" indicator + "Anulează" reset button + "Salvează toate setările" button (disabled until dirty).
- ✅ **Privacy**: user emails are hidden from public `/api/users/{id}` responses; only the owner and admins receive the `email` field.
- ✅ **Page title sync**: `<title>` resets to the site default when navigating back from /watch/:id → /.
- ✅ **Resolution badge fix**: thumbnail badge now considers `max(rendition heights, original_height, original_width)` so 4K-source videos always display the 4K badge.
- ✅ **SEO Dashboard with Google Search Console API (Feb 2026)** — new Admin → SEO tab. Admin uploads a Google service-account JSON + GSC site URL; backend validates JSON shape + runs a smoke `searchanalytics.query`; dashboard endpoint returns totals (clicks/impressions/CTR/position), top pages, top queries, and "zombie" video pages (published episodes with 0 impressions in window). Credentials stored in `settings.gsc_service_account_json` + `gsc_site_url`. UI shows period selector (7/28/90 days), metric cards, ranked tables, and an unindexed-episodes list with direct URLs. Endpoints: `POST/DELETE /api/admin/seo/credentials`, `GET /api/admin/seo/dashboard?days=N`. Tests: `/app/backend/tests/test_iteration9_seo.py` (13/13 pass).
- ✅ **Google Indexing API — Request indexing buttons (Feb 2026)** — every zombie row has a "Index" button + a bulk "Index toate (N)" button that calls `POST /api/admin/seo/request-indexing` with `{urls: [...]}` (cap 50 per call). Endpoint uses the same GSC service account with the `indexing` scope to publish `URL_UPDATED` notifications. Quota ~200/day per Google project; per-URL error from Google is surfaced in the response.
- ✅ **Video player poster fix (Feb 2026)** — `VideoPlayer.jsx` now renders an overlay `<img>` poster on top of the `<video>` element, guaranteeing the thumbnail shows before first play regardless of browser-specific behaviour (Chrome/Firefox sometimes drop `<video poster>` once metadata loads). Falls back to `thumbnail_options[0]` for legacy videos with no admin-picked primary. Wrapper also gets `background-image` CSS for double safety. Hidden the moment the `playing` event fires.
- ✅ **Big central play button + controls z-index fix (Feb 2026)** — added a YouTube-style large round play button overlaying the poster (`data-testid=player-big-play`), visible until first play. Z-index layering corrected (poster z-10, big-play z-20, controls + skip bubble z-30) so the bottom control bar (play, volume, CC, resolution, fullscreen) is never hidden behind the video.
- ✅ **Numbered pagination (Feb 2026)** — replaced "Load more" with classic numbered pagination on `/popular`, `/discover`, `/shorts`, `/all-episodes`, and `/category/:id`. URLs are SEO-friendly: `/popular/page/2`, `/category/<id>/page/3`. New shared component at `/app/frontend/src/components/Pagination.jsx` with ellipsis logic. Backend `/api/videos/count` accepts all the same filters as `/api/videos` (q, access_tier, category_ids, kind).
- ✅ **EN/RO translation expansion (Feb 2026)** — Shop page fully translated (`shop.*` namespace), "monede"→"coins" via `common.coins`, rarity labels translated, all hardcoded RO strings replaced with `t()` calls. Categories: new `name_en` field on `Category` model + Admin UI to edit it; new `categoryLabel(c, lang)` helper auto-picks the right name. Used in LeftSidebar, Watch, Upload, VideoList Discover filter, Category page.
- ✅ **Discord widget in right sidebar (Feb 2026)** — `DiscordWidget.jsx` mounts under LiveChat on home/listing pages. Two modes: (1) when `discord_guild_id` is configured AND server widget is enabled, embeds the official Discord iframe (`https://discord.com/widget?id={GUILD_ID}&theme=dark`) showing live members + #general; (2) otherwise renders a styled "#general · Join our community" card linking to `discord_invite_url` (default `https://discord.gg/5dGdSbzT4E`). Admin → Settings → "Discord community" has both fields + setup instructions. Toggle `discord_widget_enabled` to enable/disable site-wide.
- ✅ **Sitemap HEAD support + canonical URL fix (Feb 2026)** — `/sitemap.xml` and `/robots.txt` now accept HEAD requests (was 405 Method Not Allowed, breaking Googlebot probes). Also fixed the "Duplicate without user-selected canonical" bug in Google Search Console: the SSR crawler HTML (`/api/og/video/:id`) was emitting `<link rel="canonical">` pointing to whatever URL Googlebot arrived at (UUID vs slug vs legacy_id), causing duplicate indexing. Now always canonicalizes to `/watch/<slug>`. Same fix applied to `SiteHead.jsx` for JS-rendered pages.
- ✅ **SEO content-quality boosters (Feb 2026)** — three-part fix to reduce "Crawled - not indexed" and "Discovered - not indexed" reports in Google Search Console:
  - **(a) Synopsis field** on `Video` model + Admin EditVideo textarea + word counter. Rendered in SSR crawler HTML as `<section><h2>Sinopsis</h2>` so each episode has unique long-form content.
  - **(b) Top 5 comments in SSR** — user-generated content is a Google quality signal. Comments fetched + rendered server-side for Googlebot without JS.
  - **(c) noindex,follow on pagination** — `SiteHead.jsx` detects `/*/page/N` URLs and sets `<meta robots="noindex, follow">` + canonical stripped of `/page/N`. Query-string URLs (`?utm=...`) also canonicalize to the clean path.
- ✅ **AI Synopsis generation with Emergent LLM Key (Feb 2026)** — one-click AI-generated synopsis via Claude Haiku 4.5 / Gemini 3 Flash / GPT-5.4 Mini. Endpoints:
  - `POST /api/admin/videos/{id}/generate-synopsis` — single video, returns preview (not saved), admin accepts via modal in EditVideo (Sparkles button next to Synopsis textarea)
  - `POST /api/admin/videos/generate-synopsis-bulk` — batch up to 100 videos, auto-saves, skips those with existing synopsis, cost estimate + confirmation in Admin → Videos bulk toolbar with checkboxes
  - `GET /api/admin/videos/synopsis-quota` — daily quota status (auto-resets midnight UTC)
  - Admin → Settings → **"✨ AI Synopsis (SEO)"** section: enable toggle, daily limit (default 50), model selector (Haiku/Gemini/Sonnet/GPT). Cost ~$0.002/generation with Haiku (~0.01 lei).
  - Rate limiting: `ai_synopsis_used_today` + `ai_synopsis_reset_date` in settings; HTTP 429 when exceeded.
  - Tested live: generated 152-word Romanian synopsis with proper SEO tone.
- ✅ **Category SSR + index.html branding fix (Feb 2026)** — Google was indexing `/category/:slug` with default SPA shell title (either "StreamHub" leak or "Emergent | Fullstack App" from default index.html). Fixes:
  - `/app/frontend/public/index.html`: `<html lang="ro">`, `<title>Loading…</title>`, generic description (was "Emergent | Fullstack App" / "A product of emergent.sh").
  - New `GET /api/og/category/{slug_or_id}` endpoint renders SSR HTML with proper `<title>Category — SiteTitle</title>`, canonical, up-to-40 recent videos in that category (skips `<img>` when thumbnail empty; skips `og:image` meta when site logo empty).
  - `crawler_og_middleware` extended to dispatch `/category/:slug`, `/videos/category/:slug` (legacy), `/popular`, `/discover`, `/shorts`, `/all-episodes`, `/shop` to appropriate SSR renderers when Googlebot / social crawlers visit.
  - Tests: `/app/backend/tests/test_iteration10_seo_crawler.py` (11/11 pass).

## Roadmap / Future improvements
- P2 — Multi-language metadata (currently `description` is single string)
- P2 — Per-user playlists / favourites
- P2 — Coin earning streaks / daily login bonus
- P2 — Frame trading between users
- P3 — Refactor `server.py` (now ~2670 lines) into `routes/` package — overdue
- P3 — Notification system (in-app bell for video ready / replies)
- P3 — `git ls-remote` validation in /admin/github/set-remote for connectivity check
- P3 — Refactor models.py into `models/` package; move chat/storage helpers to `services/`
- P3 — Atomicity: wrap `_award_coins` (user.coins $inc + coin_ledger insert) in a Mongo transaction.

## Test data
- Admin: `admin@streamhub.io` / `Admin123!` (10 000 coins seeded for shop testing)
- Owner: `owner@streamhub.io` / `Owner@2026!`
- Tests: latest report `/app/test_reports/iteration_6.json` (12/12 backend + 11/11 frontend = 100% pass). Test file `/app/backend/tests/test_iteration6.py`.

## Deployment
- See `/app/deploy/README.md` then `sudo bash /app/deploy/scripts/install.sh`.
- Migration: `python3 deploy/migrate/parse_legacy_dump.py --sql dump.sql --out-dir ./out --all-pro --wasabi-base-url …` then `bash deploy/migrate/import_to_mongo.sh`.
