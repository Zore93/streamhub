#!/usr/bin/env python3
"""Focused bug verification for legacy video docs missing uploader_id.

Tests only the reported flow:
- PATCH /api/videos/{id} for legacy/normal ownership cases
- POST /api/videos/{id}/subtitles for legacy doc with missing uploader_id, using .vtt to avoid ffmpeg
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
import jwt
from dotenv import dotenv_values
from pymongo import MongoClient


ROOT = Path("/app")
BACKEND_ENV = dotenv_values(ROOT / "backend" / ".env")
MONGO_URL = BACKEND_ENV.get("MONGO_URL", "mongodb://localhost:27017").strip('"')
DB_NAME = BACKEND_ENV.get("DB_NAME", "test_database").strip('"')
API_BASE = os.environ.get("API_BASE", "http://localhost:8001/api")

RUN_ID = f"bug16_{int(time.time())}_{uuid.uuid4().hex[:8]}"
ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASSWORD = "Admin123!"


def make_token(user_id: str, jwt_secret: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + 86400}, jwt_secret, algorithm="HS256")


def detail(resp: httpx.Response):
    try:
        return resp.json()
    except Exception:
        return resp.text[:500]


def main() -> int:
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    results = []
    seeded_ids = []
    seeded_user_ids = []

    def record(name, passed, response=None, expected=None, note=""):
        row = {"name": name, "passed": bool(passed), "expected": expected, "note": note}
        if response is not None:
            row["status_code"] = response.status_code
            row["body"] = detail(response)
        results.append(row)
        status = "PASS" if passed else "FAIL"
        print(f"{status}: {name} :: {note}")
        if response is not None:
            print(f"  HTTP {response.status_code}: {row['body']}")

    try:
        # Verify required admin credentials and use the real auth path for admin.
        with httpx.Client(timeout=20) as http:
            login = http.post(
                f"{API_BASE}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            )
        if login.status_code != 200:
            record("admin login with provided credentials", False, login, "200")
            print(json.dumps({"results": results}, indent=2))
            return 2
        admin_token = login.json()["token"]
        admin_user = login.json()["user"]
        record("admin login with provided credentials", True, login, "200")

        settings = db.settings.find_one({"_id": "main"}) or {}
        jwt_secret = settings.get("jwt_secret")
        if not jwt_secret:
            record("read runtime jwt_secret from Mongo settings", False, None, "jwt_secret present")
            print(json.dumps({"results": results}, indent=2))
            return 2

        owner_id = f"{RUN_ID}_owner"
        other_id = f"{RUN_ID}_other"
        owner_user = {
            "id": owner_id,
            "email": f"{RUN_ID}_owner@example.com",
            "username": f"{RUN_ID}_owner",
            "password_hash": "not-used",
            "role": "user",
            "is_pro": False,
            "email_verified": True,
            "coins": 0,
            "owned_frames": [],
            "created_at": "2026-07-01T00:00:00+00:00",
        }
        other_user = {**owner_user, "id": other_id, "email": f"{RUN_ID}_other@example.com", "username": f"{RUN_ID}_other"}
        db.users.insert_many([owner_user, other_user])
        seeded_user_ids.extend([owner_id, other_id])
        owner_token = make_token(owner_id, jwt_secret)
        other_token = make_token(other_id, jwt_secret)

        legacy_id = f"{RUN_ID}_legacy"
        normal_id = f"{RUN_ID}_normal"
        # Deliberately omit uploader_id and synopsis from legacy_doc.
        legacy_doc = {
            "id": legacy_id,
            "title": "Legacy Missing Uploader",
            "description": "legacy seed",
            "tags": [],
            "uploader_username": "legacy-migrated",
            "thumbnail_url": "old-thumb.jpg",
            "thumbnail_options": ["old-thumb.jpg", "new-thumb.jpg"],
            "duration_sec": 10,
            "status": "ready",
            "progress": 100,
            "renditions": [],
            "subtitles": [],
            "access_tier": "free",
            "is_short": False,
            "views": 0,
            "likes": [],
            "created_at": "2026-07-01T00:00:00+00:00",
        }
        normal_doc = {
            **legacy_doc,
            "id": normal_id,
            "title": "Normal Owner Video",
            "slug": f"normal-owner-video-{RUN_ID[-6:]}",
            "synopsis": "normal synopsis",
            "uploader_id": owner_id,
            "uploader_username": owner_user["username"],
            "thumbnail_url": "normal-old-thumb.jpg",
            "thumbnail_options": ["normal-old-thumb.jpg", "normal-new-thumb.jpg"],
        }
        db.videos.insert_many([legacy_doc, normal_doc])
        seeded_ids.extend([legacy_id, normal_id])
        record("seed legacy and normal videos", True, None, "seeded docs")

        headers_admin = {"Authorization": f"Bearer {admin_token}"}
        headers_owner = {"Authorization": f"Bearer {owner_token}"}
        headers_other = {"Authorization": f"Bearer {other_token}"}

        with httpx.Client(timeout=30) as http:
            # 1. Legacy doc without uploader_id as admin: PATCH thumbnail must be OK and response normalized with synopsis.
            r = http.patch(
                f"{API_BASE}/videos/{legacy_id}",
                headers=headers_admin,
                json={"thumbnail_url": "new-thumb.jpg"},
            )
            body = detail(r)
            record(
                "PATCH legacy missing uploader_id as admin changes thumbnail",
                r.status_code == 200 and isinstance(body, dict) and body.get("thumbnail_url") == "new-thumb.jpg" and body.get("synopsis") == "",
                r,
                "200 with thumbnail_url=new-thumb.jpg and synopsis=''",
            )

            # 2. Legacy doc without uploader_id as non-admin: secure 403, not KeyError/500.
            r = http.patch(
                f"{API_BASE}/videos/{legacy_id}",
                headers=headers_other,
                json={"thumbnail_url": "should-not-save.jpg"},
            )
            body = detail(r)
            record(
                "PATCH legacy missing uploader_id as non-admin is denied",
                r.status_code == 403 and "Not your video" in json.dumps(body),
                r,
                "403 Not your video",
            )

            # 3. Normal doc with uploader_id as admin: OK.
            r = http.patch(
                f"{API_BASE}/videos/{normal_id}",
                headers=headers_admin,
                json={"thumbnail_url": "normal-admin-thumb.jpg"},
            )
            body = detail(r)
            record(
                "PATCH normal doc as admin succeeds",
                r.status_code == 200 and isinstance(body, dict) and body.get("thumbnail_url") == "normal-admin-thumb.jpg",
                r,
                "200",
            )

            # 4. Normal doc as a different non-admin: secure 403.
            r = http.patch(
                f"{API_BASE}/videos/{normal_id}",
                headers=headers_other,
                json={"thumbnail_url": "normal-other-thumb.jpg"},
            )
            body = detail(r)
            record(
                "PATCH normal doc as different non-admin is denied",
                r.status_code == 403 and "Not your video" in json.dumps(body),
                r,
                "403 Not your video",
            )

            # 5. Normal doc as owner: OK.
            r = http.patch(
                f"{API_BASE}/videos/{normal_id}",
                headers=headers_owner,
                json={"thumbnail_url": "normal-owner-thumb.jpg"},
            )
            body = detail(r)
            record(
                "PATCH normal doc as owner succeeds",
                r.status_code == 200 and isinstance(body, dict) and body.get("thumbnail_url") == "normal-owner-thumb.jpg",
                r,
                "200",
            )

            # User also reported subtitle upload still fails with same error. Use .vtt so ffmpeg is not involved.
            files = {"file": ("caption.vtt", b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n", "text/vtt")}
            data = {"language": "en", "label": "English"}
            r = http.post(
                f"{API_BASE}/videos/{legacy_id}/subtitles",
                headers=headers_admin,
                files=files,
                data=data,
            )
            body = detail(r)
            record(
                "POST subtitle .vtt to legacy missing uploader_id as admin does not KeyError",
                r.status_code != 500 and "uploader_id" not in json.dumps(body),
                r,
                "not 500 / no uploader_id KeyError",
                note="This specifically checks the subtitle-upload symptom from the user report, without ffmpeg.",
            )

        print("\nRESULT_JSON_START")
        print(json.dumps({"run_id": RUN_ID, "admin_user": admin_user, "results": results}, indent=2, default=str))
        print("RESULT_JSON_END")
        return 0 if all(r["passed"] for r in results) else 1
    finally:
        if seeded_ids:
            db.videos.delete_many({"id": {"$in": seeded_ids}})
        if seeded_user_ids:
            db.users.delete_many({"id": {"$in": seeded_user_ids}})
        client.close()


if __name__ == "__main__":
    sys.exit(main())