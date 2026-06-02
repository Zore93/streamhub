# StreamHub configuration — `.env` vs MongoDB

After the latest update, **almost everything configurable** lives in MongoDB
and can be edited from **Admin → Settings** without touching any file on the
server. Only true infrastructure values (the ones the backend needs *before*
it can talk to the database) remain in `.env`.

## What stays in `/opt/streamhub/deploy/.env`

| Variable          | Why it must stay in `.env`                                  |
| ----------------- | ----------------------------------------------------------- |
| `MONGO_URL`       | Required to connect to the database in the first place.     |
| `DB_NAME`         | Same as above.                                              |
| `DOMAIN`          | Used by nginx + certbot to issue the TLS cert.              |
| `LETSENCRYPT_EMAIL` | Sent to Let's Encrypt for renewal notices.                |
| `MONGO_ROOT_USER` / `MONGO_ROOT_PASSWORD` | Provisions the database container itself. |
| `UPLOAD_DIR`      | Host path bind-mounted for the upload volume.               |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Only read at first install to seed the admin user; ignored afterwards. |

## What's now in MongoDB (Admin → Settings tabs)

| Setting              | Tab                  | Default                            |
| -------------------- | -------------------- | ---------------------------------- |
| `jwt_secret`         | (auto-generated)     | 86-char random URL-safe on first boot |
| `stripe_secret_key`  | Stripe               | falls back to `$STRIPE_API_KEY` env |
| `stripe_publishable_key` | Stripe           |                                    |
| All Wasabi/S3 fields | Storage              |                                    |
| CloudFront key pair  | CloudFront           |                                    |
| SMTP host/port/user/password/from/TLS | SMTP    |                                    |
| Contact email        | Contact form         |                                    |
| Site title / desc / favicon / SEO meta | Site/SEO   | "StreamHub" / generic              |
| Password complexity / rate-limit | Auth security |                                    |
| FFmpeg concurrency / enabled resolutions / max upload MB / allow uploads | FFmpeg & Uploads | 2 / 360/720/1080 / 1024 / true |
| Allow video download | FFmpeg & Uploads     | false                              |
| Signed-URL TTL       | Signed URL Protection| 300 s                              |
| Announcements / packages / categories | dedicated tabs |                              |

## Changing a setting

1. Log in as an admin and open **/admin → Settings**.
2. Edit any field.
3. Click **Save All Settings**.
4. Hot-applied immediately for most settings. For settings that affect a
   restart-only path (very rare; e.g. ffmpeg_concurrency takes effect on the
   next transcode), no restart is needed either — they're reread per request.

## Rotating the JWT signing secret

Just blank the **`jwt_secret`** field in Admin → Settings and save —
on the next backend reload it auto-regenerates a fresh 86-char value
(everyone gets logged out, which is what you want when rotating).
