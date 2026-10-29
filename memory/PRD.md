## Iteration 28 — Preview clips, Weekly Top & Trending, Emoji reactions, Expiration emails, Watch Party (Feb 2026)

### Feature 1 — 15s/30s Preview clips for non-paying users
- **Transcoder**: new `extract_preview_clip()` function in `transcoder.py` — fast `-c copy` path with libx264 CRF 24 fallback, auto-caps duration if source is shorter.
- **process_video (server.py)**: generates `_preview15.mp4` for XXX Shorts and `_preview30.mp4` for everything else; uploaded to Wasabi when configured.
- **Video model**: added `preview_url` + `preview_duration`.
- **GET /videos/{id}**: locked PRO/VIP videos now return `preview_url` + `locked_tier` (used by frontend to route to /pro vs /vip).
- **Watch.jsx**: new `PreviewPlayer` sub-component — plays the teaser clip, clamps `currentTime` so seeking past the preview snaps back, shows a brand-accent paywall overlay at end with "Devino PRO/VIP" CTA + "Redă din nou" replay. Free videos play as normal (bypass the preview path entirely).

### Feature 2 — Top 10 Săptămânal + Trending pages (6 verticals, single page with tabs)
- **New collections**: `video_views_weekly` (iso_week bucket) and `video_views_daily` (day bucket). Both upserted on every `POST /videos/{id}/view`.
- **New endpoints**: `GET /top-weekly?vertical=&week=&limit=` and `GET /trending?vertical=&limit=` with aggregated views + joined video doc projection.
- **Verticals mapped**: `hentai, anime, filme, seriale, drama, xxx`.
- **New pages**: `TopWeekly.jsx` (routes `/top`, `/top/:vertical`, `/top/:vertical/:week`) + `Trending.jsx` (`/trending`, `/trending/:vertical`). Hentai is the default tab. Numbered gold/silver/bronze badges on positions 1–3.
- **Sidebar**: added "Top 10 Săptămânal" (Crown) and "Trending acum" (TrendingUp) nav links at the top.
- **SEO**: `SiteHead` on both pages emits dynamic title + description per vertical+week combination; URLs stable so historic weeks remain indexable.

### Feature 3 — Timeline emoji reactions (Anime / Seriale TV / Filme only)
- **New collection**: `video_reactions` with `{video_id, user_id, emoji, timestamp_sec}`. Fixed 10-emoji set in `models.REACTION_EMOJIS` (`😂 🔥 💔 😱 🥰 👏 🤔 😭 💀 🙌`).
- **Endpoints**: `GET /videos/{id}/reactions` (public) + `POST /videos/{id}/reactions` (auth, rate-limited 30/hour/video/user).
- **Backend guard**: `_reactions_enabled_for` rejects shorts and hentai. Frontend also hides picker via `enableReactions={!video.is_short && !video.is_hentai}`.
- **VideoPlayer**: emoji picker in top-right (fades with controls), reaction markers on the seek bar (rose dots clustered by timestamp), floating-bubble animation (`animate-reaction-float` keyframes in `App.css`) that drifts up on the right side as reactions fire during playback. Local reactions are optimistic; seek-back replays bubbles.

### Feature 4 — Subscription expiration emails
- **mailer.py** stays unchanged; new helper `_send_expiry_mail(settings, email, tier, phase, when_iso)` in `server.py` renders RO-copy for 3 phases: 3 days before, on expiry day, after expiry.
- **New endpoint**: `POST /api/cron/subscription-expiry` — HMAC-authed via `WEBHOOK_CRON_SECRET`, enqueues `_run_subscription_expiry_cron` in BackgroundTasks and acks 200 immediately (follows the Emergent cron contract).
- **Idempotency**: user docs get stamped with `pro_exp_notified_{3d,today,expired}` and `vip_exp_notified_{3d,today,expired}` so each phase mails at most once.
- **.emergent/crons.yml**: new file — single cron running daily at 09:00 Europe/Bucharest.
- **backend/.env**: added `WEBHOOK_CRON_SECRET` (strong random 32+ chars).

### Feature 5 — Watch Party (synchronized co-view + chat)
- **New collection**: `watch_parties` with 6-char uppercase alnum `code`, host info, member count.
- **Endpoints**: `POST /parties` (anyone, guest-friendly), `GET /parties/{code}` returns party + playable video.
- **WebSocket**: `/api/parties/{code}/ws` with in-memory `_PARTY_ROOMS` dict. Max 10 members per room. Messages: `join`, `sync {play|pause|seek, t}`, `chat`, `ping`. Host-less — any member can drive playback; `suppress` flag on each client prevents remote-sync echo loops.
- **New page**: `WatchParty.jsx` — join screen (name picker), native `<video>` with controls, shareable code + copy-link button, 320px chat sidebar with member list.
- **Watch.jsx**: new "Watch Party" button next to Report, calls `POST /parties` and navigates to `/party/:code`.
- **Routes**: `/party/:code` added to `App.js`.

### Smoke tests performed
- Backend: `/trending`, `/top-weekly`, `/parties` CRUD, `/videos/{id}/reactions` GET+POST, cron endpoint auth + valid secret → 200.
- Frontend: `/top` renders 6 tabs with Hentai default; Watch page shows emoji picker + Watch Party button; sidebar has both new entries.



## Iteration 27 — Storage stats, live encoding progress, CC hint, episode number centered, 1080p encoding fix (Feb 2026)
- **Backend `transcoder.probe_video` bug fix**: Previously used the FIRST video stream, which may be an attached-picture (MKV cover art) with tiny dimensions — the main video stream was ignored, so 1080p sources could be probed as e.g. 320×320 and only output 720p. New logic picks the LARGEST video stream (by pixel count) while preferring streams whose `disposition.attached_pic` flag is 0. Added detailed logging with full candidate list.
- **Backend `transcoder.ENCODE_PROFILES`**: Added `"default"` profile (preset `veryfast`, CRF 23) and made it the new DEFAULT. Matches the original fast encoding behaviour before per-profile compression was introduced. Existing profiles (`original`, `balanced`, `strong`, `max`) all pinned to preset `slow` for best compression.
- **Backend `transcoder.transcode_to_resolution`**: `preset` now comes from the profile dict instead of being hard-coded to `slow`. Added info log line emitted at the start of each rendition with chosen res, crf, maxrate, preset.
- **Backend `process_video`**: Added per-rendition size tracking into `compressed_size_bytes` on the `Video` doc, plus stamps `encode_profile` used at transcode time. New info logs: source WxH, enabled resolutions, chosen resolutions, size of each rendition in MB. Failed renditions now log explicitly instead of being silently skipped.
- **Backend `models.Video`**: Added `compressed_size_bytes: int` and `encode_profile: str`.
- **Backend `models.AppSettings`**: Default `encode_profile` is now `"default"` (was `"original"`).
- **Backend new endpoint `GET /api/admin/storage-stats`**: Returns aggregated totals (video count, original bytes, compressed bytes, saved bytes, saved %), a per-profile breakdown, and a paginated per-video table. Only counts videos with `status=ready` AND both size fields populated.
- **Frontend `Admin.jsx` → Storage tab (new)**: Totals cards + per-profile breakdown table + per-video paginated table with search; uses a shared `formatBytes` helper and friendly profile labels (`PROFILE_LABELS`).
- **Frontend `Admin.jsx` → Videos tab**: Each processing video now shows a live `EncodingProgressBar` (gradient rose→amber bar + percent). While any processing video is visible the list auto-refreshes every 4s.
- **Frontend `Admin.jsx` → Settings → Compresie video**: Added "Default (rapid)" as the first profile option (preset `veryfast` like before compression profiles existed). Settings now default `encode_profile` to `"default"`.
- **Frontend `Watch.jsx`**: New brand-accent chenar below the Like / Report row shown ONLY when the video has at least one subtitle track. Contains RO + EN instructions with an inline `Subtitles` (CC) icon replacing the literal "CC" text, matching the icon in the player bar. Rose→amber gradient border with left ribbon.
- **Frontend episode thumbnails (7 pages)**: `Ep X` badge moved from `top-left corner` to **centered over the thumbnail** (bigger font, bordered pill with backdrop-blur) on `HentaiSeriesDetail`, `HentaiSeasonDetail`, `AnimeSeriesDetail`, `AnimeSeasonDetail`, `TvSeriesDetail`, `TvSeasonDetail`, `ShortsSeriesDetail`. Uses `pointer-events-none` so clicks still reach the underlying `VideoCard`.

### Important operator note (1080p encoding)
During investigation we found the admin's `enabled_resolutions` setting was `["360p", "720p"]` — this would ALSO cap 1080p sources at 720p regardless of any probe fix. If the admin wants 1080p outputs they must check `1080p` in Admin → Settings → Enabled resolutions.



## Iteration 26 — Home redesigned around Hentai + sidebar cleanup (Feb 2026)
- **Home page**: Removed "Ultimele Încărcări" (generic latest) section and replaced it with "Ultimele episoade hentai adăugate" (last 12 hentai videos from `/videos?section=latest&kind=video&is_hentai=true`). New section lives inside the `showHentai` gate, so it shows on "Toate" tab and "Hentai RoSub" tab.
- **Home tabs**: Removed "Videoclipuri" tab (no longer meaningful since generic latest section was dropped). Also removed `latest`/`popular`/`showVideos` state in `Home.jsx`.
- **Sidebar**: Removed "Toate Episoadele" (`/all-episodes`) nav entry from `LeftSidebar.jsx` and `ListVideo` icon import.
- **Routes**: Deleted `/all-episodes` and `/all-episodes/page/:page` routes from `App.js`. `VideoList.jsx` `"all"` variant and `titleKey: "page.allEpisodes"` dropped (file retained for /popular, /discover, /shorts, /anime/all).
- **Backend `/videos` + `/videos/count`**: Added `is_hentai: Optional[bool]` query param. Hentai videos now also surface in Popular (sorted by views) and Discover (random `$sample`) because the hard `is_hentai = {$ne: True}` guard no longer applies when `section in ("popular", "random")` and no explicit hentai filter is supplied.
- **i18n**: Added `home.lastHentaiEpisodes` ("Ultimele episoade hentai adăugate" / "Latest hentai episodes added").
- Smoke test (Playwright): sidebar no longer contains "Toate Episoadele"; home tabs = `[Toate, XXX Shorts, Drama Shorts, Anime, Hentai RoSub, Seriale TV, Filme RoSub]`. Backend curl verified `is_hentai=true` filter and new popular/random visibility.


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
- ✅ **VIP subscription tier (Feb 2026)** — separate premium tier alongside PRO. Access hierarchy: VIP sees Free+PRO+VIP; PRO sees Free+PRO; Free sees Free. Legacy videos untouched (backend `$or` query treats packages missing `tier` field as `pro`).
  - **Model**: `Package.tier` ("pro"|"vip"); `User.is_vip`, `vip_package_id`, `vip_expires_at`; `Video.access_tier` accepts "vip".
  - **Backend**: `/api/packages?tier=pro|vip` filter, admin `POST /api/packages` accepts `tier`, `POST /api/admin/users/{id}/grant-vip` & `revoke-vip` mirror PRO endpoints, VIP expiry auto-check on login (mirrors PRO), Stripe checkout/webhook credits `is_vip` when package `tier=="vip"`, `get_video` enforces hierarchy (VIP super-set of PRO), `PATCH /videos/{id}` validates `access_tier ∈ {free,pro,vip}`.
  - **Frontend**: `/vip` page with gold `vip-gradient-text` title lists tier=vip packages via Stripe; Admin → new "Packages VIP" tab (`tab-packages-vip`); EditVideo dropdown gains "VIP only" option; `VideoCard` renders gold `vip-badge-<id>` top-right; Watch shows "Conținut VIP" locked overlay + gold `watch-vip-badge`; LeftSidebar has `nav-vip` Crown link.
  - **CSS**: new `.vip-gradient`, `.vip-gradient-text`, `.vip-border-gradient` (gold `#fde047 → #f59e0b → #b45309`).
  - Tests: `/app/backend/tests/test_iteration18_vip.py` (20/20 pass).

## Roadmap / Future improvements
- P0 — Refactor `server.py` (now ~5330 lines) into `routers/` package (videos, admin, series, seo, anime) — overdue
- P1 — Save Home Tab in URL (`?v=drama|xxx|anime`) for direct linking & refresh persistence
- P1 — Backfill `uploader_id` script for SQL-migrated legacy video docs
- P2 — Drag-and-drop episode reordering (Admin: Shorts + Drama + Anime seasons)
- P2 — AI-generated season synopsis (`AnimeSeason.synopsis` field already exists — wire up)
- P2 — Multi-language metadata (currently `description` is single string)
- P2 — Per-user playlists / favourites
- P2 — Coin earning streaks / daily login bonus
- P2 — Frame trading between users
- P3 — Notification system (in-app bell for video ready / replies)
- P3 — Refactor models.py into `models/` package; move chat/storage helpers to `services/`
- P3 — Suppress announcement DialogOverlay on /login and /register (pointer blocking pre-existing)

## Iteration 24 — Filme RoSub + SSR OG + Mobile Fullscreen (Feb 2026)
- **Filme RoSub vertical** (option 2-B: multi-category, no cover per user request):
  - Model: `FilmCategory { id, name, slug, description, active, position }`; `Video` gains `is_film_rosub: bool` + `film_category_ids: List[str]` (mutually exclusive with `is_short` and `is_anime`).
  - Backend routes (server.py ~1400-1530): CRUD `/api/film-categories(+/all|/{key})`, `GET /api/videos/filme?category_id=…`. Default `/api/videos` filters films out (`$ne True`); admin & upload flows opt-in via `is_film_rosub=true`. Cascade `$pull` on category delete.
  - Frontend: sidebar link `/filme-rosub` (Film icon), page `FilmeRoSub.jsx` with horizontal text-only category chip row + film grid, route `/filme-rosub/:catSlug` filters by category (chip goes rose). Admin tab `FilmCategoriesTab` (text CRUD only). Upload+EditVideo have exclusive `Este film RoSub` toggle → multi-select chip picker for categories. Home page adds `Filme RoSub` vertical tab + `section-filme` row.
- **SSR OG for series/season/filme pages** — fixed Discord/Facebook embeds:
  - New backend endpoints (server.py ~4680-4930): `/api/og/shorts-series/{slug}`, `/api/og/anime-series/{slug}`, `/api/og/anime-season/{s}/{sk}`, `/api/og/filme-rosub`, `/api/og/filme-rosub/{cat}`. Shared `_og_html_response` renderer for consistent OG+Twitter+canonical+robots meta.
  - Middleware `crawler_og_middleware` (server.py ~5720) matches these routes with UA sniff. Nginx production template (`deploy/nginx/streamhub.conf.template`) mirrors rewrites for `/anime/series/*/*`, `/anime/series/*`, `/shorts/series/*`, `/filme-rosub[/…]`, `/category/*`. Fallback strategy: unknown slug returns home OG (crawler-friendly) not 404.
- **Mobile pseudo-fullscreen (VideoPlayer.jsx)**:
  - `toggleFullscreen` detects iOS/Android UA or missing `document.fullscreenEnabled` → toggles `pseudoFS` state applying `fixed inset-0 z-[9999] !w-screen !h-[100dvh]` (portrait, no rotate). ESC exits, body scroll locked. Native Fullscreen API still used on desktop. Icon toggles Maximize↔Minimize.
- **Also fixed**: accidental removal of `@api.get("/videos")` decorator restored (regression from earlier edit).
- Tests: `/app/backend/tests/test_iteration24_filme_rosub.py` — **27/27 PASS**.

## Iteration 25 — Admin/public pagination + Reports (Jun 2026)
- Home: "Ultimele episoade hentai adăugate" replaces "Ultimele Încărcări"; removed "Videoclipuri" tab and "Toate Episoadele" sidebar link. Hentai episodes included in Populare/Descoperă/Categorii.
- Series dropdown limits raised 200 → 5000 (Edit Video).
- Admin series tabs (Anime, Hentai, Shorts, TV, Categorii): 100/page pagination + search by name.
- Hentai "Vezi mai multe" → `/hentai/all`.
- Reports: `POST/GET/DELETE /api/reports`, "Raportează" button + modal on Watch, "Rapoarte" tab in Admin.
- Public series pages (`/hentai`, `/seriale-tv`, `/anime`, `/shorts`, `/drama-shorts`): pagination REMOVED at user request — all series on a single page (search still filters).

- Fix (Jun 2026): series/season slugs with "?", "!", spaces broke public links ("Această serie nu există"). Now `slugify()` is applied on create/patch for all series+seasons, and startup `_fix_unsafe_series_slugs()` auto-cleans existing unsafe slugs (unique per collection / per series for seasons).
- Compresie video (Jun 2026): `transcoder.ENCODE_PROFILES` (original crf20 / balanced crf23 / strong crf25 / max crf27) + per-height maxrate caps, preset slow, H.264 high. Setting `encode_profile` (default "original") selectable in Admin → Setări (EncodeProfilePicker cu descrieri de calitate). Test: sursă 58.5MB → 14.8/10.1/7.1/5.1 MB.

## Backlog
- P0: Split `server.py` (~6600 lines) into routers.
- P1: Backfill `uploader_id` on legacy videos.
- P2: Home vertical tab in URL (`?v=`); drag-and-drop episode reorder in Admin.

## Iteration 23 — Anime Seasons layer (Feb 2026)
- **Goal**: multi-season structure for Anime (Option 2 from Chat), no migration needed.
- **Model**: NEW `AnimeSeason { id, series_id, number, title, slug, description, synopsis, cover_thumbnail, year, season_type (season|ova|movie|special), position, active }`. Video gains `anime_season_id` (denormalised `anime_series_id` remains — derived from season on write).
- **Backend routes** (`server.py` ~1080-1370): GET `/anime-series/{sid}/seasons` (public active-only), `/seasons/all` (admin, incl. inactive), POST `/anime-series/{sid}/seasons`, GET `/anime-seasons/{key}` (id or slug), GET `/anime-series/{ss}/seasons/{sk}` (pair — for public URL), PATCH/DELETE `/anime-seasons/{id}` (delete blocked if has episodes), POST `/anime-seasons/{id}/cover` (Wasabi or local). `POST /videos/upload/{id}/finish` derives `anime_series_id` + `anime_series_position` (auto = last+1) from `anime_season_id`. `PATCH /videos/{id}` re-derives series when season changes. Cascade delete on series removes seasons + detaches videos.
- **Frontend**: `/anime/series/{slug}` rewritten — grid of seasons w/ cover + type badge + episode_count; falls back to episode grid for legacy series. NEW `/anime/series/{seriesSlug}/{seasonSlug}` (AnimeSeasonDetail) — episode list of a season. Admin → Serii Anime: new "Sezoane" toggle per series opens `AnimeSeasonsManager` with create-form (Nr/Type/Title/Slug/Year/Description/Cover/Active) + per-season row (cover upload on click, number/position inputs, toggle, delete). Upload.jsx + EditVideo.jsx: cascade Serie → Sezon dropdowns; changing series resets season. Watch.jsx autoplay next-episode extended to `anime_season_id` (stays within season).
- **Also fixed in this session**: chunked upload `/finish` 500 caused by cross-device `Path.rename` between `/tmp/streamhub_stage` (chunk staging) and `/app/uploads/originals` → replaced with `shutil.move`. Refactored 9 upload endpoints (avatar/cover/series_cover/anime_cover/anime_season_cover/branding/subtitles/original/chunks) to stage into `/tmp` via `tempfile.mkstemp`, then Wasabi-upload or `_finalize_upload` fallback into UPLOAD_DIR — unblocks the `ephemeral-upload-storage` linter cleanly.
- Tests: `/app/backend/tests/test_iteration23_anime_seasons.py` (16/16 pass), Playwright covered `/anime/series/{s}`, `/anime/series/{s}/{sk}`, admin toggle-seasons manager. Report `/app/test_reports/iteration_23.json`.

## Test data
- Admin: `admin@streamhub.io` / `Admin123!` (10 000 coins seeded for shop testing)
- Owner: `owner@streamhub.io` / `Owner@2026!`
- Tests: latest report `/app/test_reports/iteration_23.json` (16/16 backend + all frontend flows = 100% pass).

## Deployment
- See `/app/deploy/README.md` then `sudo bash /app/deploy/scripts/install.sh`.
- Migration: `python3 deploy/migrate/parse_legacy_dump.py --sql dump.sql --out-dir ./out --all-pro --wasabi-base-url …` then `bash deploy/migrate/import_to_mongo.sh`.
