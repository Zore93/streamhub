"""
Convert a phpMyAdmin SQL dump from the legacy hentairosub.ro / WoWonder video
platform into MongoDB-ready JSON files that match the StreamHub schema.

Outputs (in --out-dir):
    users.json          one JSON document per line
    categories.json
    videos.json
    legacy_id_maps.json human-readable mapping legacy_id -> new uuid

Usage:
    python parse_legacy_dump.py \
        --sql /path/to/loadingv_video.sql \
        --out-dir ./out \
        --wasabi-base-url "https://s3.wasabisys.com/your-bucket"   # optional
        --include-only-active                                       # optional

The MongoDB import script (deploy/migrate/import_to_mongo.sh) then ingests these
JSON files into a running StreamHub install.

Why this approach?
  - The legacy DB is MySQL/MariaDB; ours is MongoDB. We can't simply dump+restore.
  - We don't depend on a live MySQL instance — we just parse the dump file once.
  - bcrypt $2y$ hashes are byte-compatible with bcrypt $2b$, so passwords keep
    working: when a user logs in we transparently re-hash if needed.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Reasonable defaults for what the legacy app calls "Pro types" (1=monthly, 2=yearly...)
PRO_TYPE_DAYS = {1: 30, 2: 90, 3: 180, 4: 365, 5: 730}


# ─────────────────────────────────────── parser ──────────────────────────────
INSERT_RE = re.compile(
    r"^INSERT INTO `(?P<table>[^`]+)`\s*\((?P<cols>[^)]+)\)\s*VALUES\s*",
    re.IGNORECASE,
)


def _tokenize_values(raw: str):
    """Split the bracketed VALUES of an INSERT into a list of column-value rows.

    Handles MySQL-style quoting:  '...', escaped \', backslashes, NULL, numbers.
    """
    rows = []
    i, n = 0, len(raw)
    while i < n:
        # skip whitespace and comma
        while i < n and raw[i] in " \t\r\n,":
            i += 1
        if i >= n or raw[i] != "(":
            break
        i += 1  # consume '('
        row = []
        cur = []
        in_str = False
        while i < n:
            c = raw[i]
            if in_str:
                if c == "\\" and i + 1 < n:  # escape sequence
                    nxt = raw[i + 1]
                    cur.append({"n": "\n", "t": "\t", "r": "\r", "0": "\0"}.get(nxt, nxt))
                    i += 2
                    continue
                if c == "'":
                    # check for escaped ''
                    if i + 1 < n and raw[i + 1] == "'":
                        cur.append("'")
                        i += 2
                        continue
                    in_str = False
                    row.append("".join(cur))
                    cur = []
                    i += 1
                    continue
                cur.append(c)
                i += 1
                continue
            # not in string
            if c == "'":
                in_str = True
                cur = []
                i += 1
                continue
            if c == ",":
                if cur:
                    val = "".join(cur).strip()
                    row.append(_coerce(val))
                    cur = []
                i += 1
                continue
            if c == ")":
                if cur:
                    val = "".join(cur).strip()
                    row.append(_coerce(val))
                    cur = []
                i += 1
                rows.append(row)
                break
            cur.append(c)
            i += 1
        else:
            # ran off end without ')'
            break
    return rows


def _coerce(s: str):
    if s == "" or s.upper() == "NULL":
        return None
    # number?
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def parse_dump(sql_path: Path, want_tables=("users", "videos", "langs")):
    """Yields ((table, columns, row-dict)) for each row of each wanted table."""
    cur_table = None
    cur_cols = []
    buf = []
    in_insert = False
    with sql_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not in_insert:
                m = INSERT_RE.match(line)
                if not m:
                    continue
                table = m.group("table")
                if table not in want_tables:
                    continue
                cur_table = table
                cur_cols = [c.strip().strip("`") for c in m.group("cols").split(",")]
                # consume the VALUES portion (rest of this line + further lines until ;)
                rest = line[m.end():]
                buf = [rest]
                in_insert = not rest.rstrip().endswith(";")
                if not in_insert:
                    joined = buf[0].rstrip().rstrip(";")
                    for row in _tokenize_values(joined):
                        yield cur_table, cur_cols, dict(zip(cur_cols, row))
                continue
            # inside multi-line insert
            buf.append(line)
            if line.rstrip().endswith(";"):
                joined = "".join(buf).rstrip().rstrip(";")
                for row in _tokenize_values(joined):
                    yield cur_table, cur_cols, dict(zip(cur_cols, row))
                in_insert = False
                buf = []
                cur_table = None


# ─────────────────────────────────────── mappers ─────────────────────────────
def parse_duration(s: str | None) -> float:
    if not s:
        return 0.0
    parts = str(s).split(":")
    try:
        if len(parts) == 3:
            h, m, sec = (int(x) for x in parts)
            return h * 3600 + m * 60 + sec
        if len(parts) == 2:
            m, sec = (int(x) for x in parts)
            return m * 60 + sec
        return float(parts[0])
    except ValueError:
        return 0.0


def epoch_to_iso(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def normalize_bcrypt(h: str) -> str:
    """`$2y$` (PHP) bytes-identical to `$2b$` (modern bcrypt) — rewrite the prefix
    so the Python `bcrypt` library accepts it without complaint."""
    if h and h.startswith("$2y$"):
        return "$2b$" + h[4:]
    return h


def video_renditions(video_loc: str, flags: dict, wasabi_base: str | None):
    """
    The legacy DB stores ONE filename in `video_location` (often the 360p
    converted file) and has 240p/360p/480p/720p/1080p/2048p/4096p int flags.
    Each flag = 1 means that rendition exists at the conventional sibling path
    (… _360p_converted.mp4 → … _720p_converted.mp4).

    The original prod hosts videos on Wasabi. If --wasabi-base-url is given,
    we prepend it to the relative paths so they're directly playable; otherwise
    the path is left relative (the user can rewrite later).
    """
    if not video_loc:
        return []
    # Replace "<res>_converted" with placeholder so we can swap
    base = video_loc
    res_re = re.compile(r"_(240|360|480|720|1080|2048|4096)p_converted")
    m = res_re.search(base)
    if not m:
        # Single URL with unknown rendition tagging — return as-is at 360p
        return [{
            "resolution": "360p", "width": 0, "height": 0,
            "url": _maybe_prefix(base, wasabi_base),
        }]
    rends = []
    for res in ("240p", "360p", "480p", "720p", "1080p", "2048p", "4096p"):
        if int(flags.get(res, 0) or 0) != 1:
            continue
        url = res_re.sub(f"_{res}_converted", base)
        rends.append({
            "resolution": res, "width": 0, "height": 0,
            "url": _maybe_prefix(url, wasabi_base),
        })
    return rends


def _maybe_prefix(path: str, base: str | None) -> str:
    if not path:
        return path
    if path.startswith(("http://", "https://")):
        return path
    if base:
        return f"{base.rstrip('/')}/{path.lstrip('/')}"
    return path


# ─────────────────────────────────────── main ────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--wasabi-base-url", default=None,
                    help="If given, all relative video/thumbnail paths are prefixed with this base.")
    ap.add_argument("--include-only-active", action="store_true",
                    help="Skip users with active=0 and videos with active=0/approved=0.")
    ap.add_argument("--all-pro", action="store_true",
                    help="Force every imported video to access_tier=pro (recommended for legacy "
                         "migrations — keeps existing catalogue behind the paywall).")
    ap.add_argument("--shorts-max-seconds", type=int, default=60,
                    help="Videos shorter than this AND vertical are tagged as Shorts.")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    users_by_legacy: dict[int, str] = {}
    cats_by_legacy: dict[int, str] = {}

    users_out = (args.out_dir / "users.json").open("w", encoding="utf-8")
    cats_out = (args.out_dir / "categories.json").open("w", encoding="utf-8")
    videos_out = (args.out_dir / "videos.json").open("w", encoding="utf-8")

    n_users = n_cats = n_videos = n_skipped = 0
    now = datetime.now(timezone.utc)

    for table, cols, row in parse_dump(args.sql, want_tables=("users", "videos", "langs")):
        if table == "langs":
            if row.get("type") != "category":
                continue
            legacy_id = int(row.get("id") or 0)
            name = (row.get("english") or row.get("lang_key") or "").strip()
            if not name or legacy_id == 0:
                continue
            new_id = str(uuid.uuid4())
            cats_by_legacy[legacy_id] = new_id
            doc = {
                "id": new_id,
                "name": name,
                "slug": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or f"cat-{legacy_id}",
                "legacy_id": legacy_id,
                "created_at": now.isoformat(),
            }
            cats_out.write(json.dumps(doc, ensure_ascii=False) + "\n")
            n_cats += 1

        elif table == "users":
            legacy_id = int(row.get("id") or 0)
            email = (row.get("email") or "").strip().lower()
            username = (row.get("username") or "").strip()
            pw = normalize_bcrypt((row.get("password") or "").strip())
            if not email or not username or not pw:
                n_skipped += 1
                continue
            if args.include_only_active and int(row.get("active") or 0) != 1:
                n_skipped += 1
                continue
            is_pro = int(row.get("is_pro") or 0) == 1
            pro_expires_at = None
            if is_pro:
                ae = row.get("active_expire")
                # active_expire can be epoch string or '0'
                try:
                    if ae and int(ae) > int(now.timestamp()):
                        pro_expires_at = epoch_to_iso(ae)
                except Exception:
                    pass
                if not pro_expires_at:
                    pro_type = int(row.get("pro_type") or 0)
                    days = PRO_TYPE_DAYS.get(pro_type, 30)
                    pro_expires_at = (now + timedelta(days=days)).isoformat()
            new_id = str(uuid.uuid4())
            users_by_legacy[legacy_id] = new_id
            doc = {
                "id": new_id,
                "email": email,
                "username": username,
                "password_hash": pw,
                "role": "admin" if int(row.get("admin") or 0) == 1 else "user",
                "is_pro": is_pro,
                "pro_package_id": None,
                "pro_expires_at": pro_expires_at,
                "email_verified": int(row.get("verified") or row.get("active") or 0) == 1,
                "verify_token": None,
                "avatar_url": _maybe_prefix(row.get("avatar"), args.wasabi_base_url)
                              if row.get("avatar") and "d-avatar" not in (row.get("avatar") or "") else None,
                "cover_url": _maybe_prefix(row.get("cover"), args.wasabi_base_url)
                             if row.get("cover") and "d-cover" not in (row.get("cover") or "") else None,
                "bio": row.get("about") or None,
                "banned_until": None,
                "banned_reason": None,
                "created_at": epoch_to_iso(row.get("time") or int(now.timestamp())),
                "legacy_id": legacy_id,
            }
            users_out.write(json.dumps(doc, ensure_ascii=False) + "\n")
            n_users += 1

        elif table == "videos":
            legacy_id = int(row.get("id") or 0)
            title = (row.get("title") or "").strip()
            video_loc = (row.get("video_location") or "").strip()
            if not title or not video_loc:
                n_skipped += 1
                continue
            if args.include_only_active and (int(row.get("active") or 0) != 1
                                             or int(row.get("approved") or 0) != 1):
                n_skipped += 1
                continue
            uploader_legacy = int(row.get("user_id") or 0)
            uploader_new = users_by_legacy.get(uploader_legacy)
            # If no matching user yet, queue with sentinel — script processes users
            # before videos in dump order, but if reversed we'd lose the link.
            if not uploader_new:
                uploader_new = "00000000-0000-0000-0000-000000000000"
            cat_new = cats_by_legacy.get(int(row.get("category_id") or 0))
            tags = (row.get("tags") or "").strip()
            tag_list = [t.strip() for t in re.split(r"[,;\n]", tags) if t.strip()]
            renditions = video_renditions(video_loc, row, args.wasabi_base_url)
            duration = parse_duration(row.get("duration"))
            # Heuristic for legacy Shorts: WoWonder doesn't have a "shorts" flag, but
            # vertical/mobile clips have orientation="portrait" or height > width.
            orientation = (row.get("video_orientation") or "").strip().lower()
            w_raw = int(row.get("video_width") or row.get("width") or 0)
            h_raw = int(row.get("video_height") or row.get("height") or 0)
            is_vertical = orientation in ("portrait", "vertical") or (h_raw > 0 and w_raw > 0 and h_raw > w_raw)
            is_short = bool(is_vertical and 0 < duration <= args.shorts_max_seconds)
            access_tier = "pro" if args.all_pro else ("pro" if int(row.get("privacy") or 0) == 2 else "free")
            doc = {
                "id": str(uuid.uuid4()),
                "title": title,
                "description": (row.get("description") or "").strip() or "",
                "tags": tag_list,
                "category_id": cat_new,
                "uploader_id": uploader_new,
                "uploader_username": "",  # back-fill in mongo if needed via $lookup
                "thumbnail_url": _maybe_prefix(row.get("thumbnail"), args.wasabi_base_url)
                                  if row.get("thumbnail") and "d-thumb" not in (row.get("thumbnail") or "")
                                  else None,
                "thumbnail_options": [],
                "duration_sec": duration,
                "original_filename": video_loc.split("/")[-1] if video_loc else "",
                "original_size_bytes": int(row.get("size") or 0),
                "original_width": w_raw,
                "original_height": h_raw,
                "status": "ready" if int(row.get("converted") or 1) == 1 else "processing",
                "progress": 100,
                "error": None,
                "renditions": renditions,
                "subtitles": [],
                "access_tier": access_tier,
                "is_short": is_short,
                "views": int(row.get("views") or 0),
                "likes": [],
                "created_at": epoch_to_iso(row.get("time") or int(now.timestamp())),
                "legacy_id": legacy_id,
                "legacy_uploader_id": uploader_legacy,
            }
            videos_out.write(json.dumps(doc, ensure_ascii=False) + "\n")
            n_videos += 1

    users_out.close(); cats_out.close(); videos_out.close()

    maps = {
        "users_legacy_to_new": users_by_legacy,
        "categories_legacy_to_new": cats_by_legacy,
        "counts": {"users": n_users, "categories": n_cats, "videos": n_videos, "skipped_rows": n_skipped},
    }
    (args.out_dir / "legacy_id_maps.json").write_text(json.dumps(maps, indent=2))

    print(f"✓ users      : {n_users}")
    print(f"✓ categories : {n_cats}")
    print(f"✓ videos     : {n_videos}")
    print(f"✓ skipped    : {n_skipped}")
    print(f"  → output dir: {args.out_dir}")


if __name__ == "__main__":
    sys.exit(main())
