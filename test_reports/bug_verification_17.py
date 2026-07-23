#!/usr/bin/env python3
"""Focused bug verification for legacy video docs missing uploader_id.

User-reported symptoms:
- Thumbnail change on already-uploaded/legacy videos failed with KeyError: uploader_id.
- Subtitle upload on the same legacy shape failed with the same KeyError.

This iteration reruns the previous PATCH/subtitle checks and adds DELETE video
and DELETE subtitle ownership checks on legacy docs without uploader_id.
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
UPLOAD_DIR = Path(BACKEND_ENV.get("UPLOAD_DIR", "/app/uploads").strip('"'))
API_BASE = os.environ.get("API_BASE", "http://localhost:8001/api")

RUN_ID = f"bug17_{int(time.time())}_{uuid.uuid4().hex[:8]}"
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


def legacy_video_doc(video_id: str, title: str, subtitles=None):
    return {
        "id": video_id,
        "title": title,
        "description": "legacy seed without uploader_id",
        "tags": [],
        "uploader_username": "legacy-migrated",
        "thumbnail_url": "old-thumb.jpg",
        "thumbnail_options": ["old-thumb.jpg", "new-thumb.jpg", "delete-thumb.jpg"],
        "duration_sec": 10,
        "status": "ready",
        "progress": 100,
        "renditions": [],
        "subtitles": subtitles or [],
        "access_tier": "free",
        "is_short": False,
        "views": 0,
        "likes": [],
        "created_at": "2026-07-01T00:00:00+00:00",
    }


def main() -> int:
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    results = []
    seeded_video_ids = []
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
        with httpx.Client(timeout=20) as http:
            login = http.post(f"{API_BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        if login.status_code != 200:
            record("admin login with provided credentials", False, login, "200")
            print(json.dumps({"run_id": RUN_ID, "results": results}, indent=2, default=str))
            return 2
        admin_token = login.json()["token"]
        record("admin login with provided credentials", True, login, "200")

        settings = db.settings.find_one({"_id": "main"}) or {}
        jwt_secret = settings.get("jwt_secret")
        if not jwt_secret:
            record("read runtime jwt_secret from Mongo settings", False, None, "jwt_secret present")
            print(json.dumps({"run_id": RUN_ID, "results": results}, indent=2, default=str))
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

        legacy_patch_id = f"{RUN_ID}_legacy_patch"
        legacy_post_id = f"{RUN_ID}_legacy_post"
        legacy_delete_admin_id = f"{RUN_ID}_legacy_delete_admin"
        legacy_delete_nonadmin_id = f"{RUN_ID}_legacy_delete_nonadmin"
        legacy_delete_sub_id = f"{RUN_ID}_legacy_delete_sub"
        existing_sub_id = f"{RUN_ID}_sub_existing"
        existing_sub_rel = f"subtitles/{legacy_delete_sub_id}_{existing_sub_id}.vtt"
        existing_sub_path = UPLOAD_DIR / existing_sub_rel
        existing_sub_path.parent.mkdir(parents=True, exist_ok=True)
        existing_sub_path.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nExisting\n", encoding="utf-8")

        normal_id = f"{RUN_ID}_normal"
        normal_doc = {
            **legacy_video_doc(normal_id, "Normal Owner Video"),
            "slug": f"normal-owner-video-{RUN_ID[-6:]}",
            "synopsis": "normal synopsis",
            "uploader_id": owner_id,
            "uploader_username": owner_user["username"],
            "thumbnail_url": "normal-old-thumb.jpg",
            "thumbnail_options": ["normal-old-thumb.jpg", "normal-new-thumb.jpg"],
        }
        docs = [
            legacy_video_doc(legacy_patch_id, "Legacy Patch Missing Uploader"),
            legacy_video_doc(legacy_post_id, "Legacy Subtitle Upload Missing Uploader"),
            legacy_video_doc(legacy_delete_admin_id, "Legacy Delete Admin Missing Uploader"),
            legacy_video_doc(legacy_delete_nonadmin_id, "Legacy Delete Nonadmin Missing Uploader"),
            legacy_video_doc(
                legacy_delete_sub_id,
                "Legacy Delete Subtitle Missing Uploader",
                subtitles=[{
                    "id": existing_sub_id,
                    "language": "en",
                    "label": "English",
                    "url": existing_sub_rel,
                    "original_url": None,
                    "format": "vtt",
                }],
            ),
            normal_doc,
        ]
        db.videos.insert_many(docs)
        seeded_video_ids.extend([d["id"] for d in docs])
        record("seed legacy/normal videos and users", True, None, "seeded docs")

        headers_admin = {"Authorization": f"Bearer {admin_token}"}
        headers_owner = {"Authorization": f"Bearer {owner_token}"}
        headers_other = {"Authorization": f"Bearer {other_token}"}

        with httpx.Client(timeout=30) as http:
            # Regression from the original thumbnail bug.
            r = http.patch(
                f"{API_BASE}/videos/{legacy_patch_id}",
                headers=headers_admin,
                json={"thumbnail_url": "new-thumb.jpg"},
            )
            body = detail(r)
            record(
                "PATCH legacy missing uploader_id as admin changes thumbnail",
                r.status_code == 200 and isinstance(body, dict) and body.get("thumbnail_url") == "new-thumb.jpg" and body.get("synopsis") == "",
                r,
                "200 with thumbnail_url=new-thumb.jpg and normalized synopsis, no KeyError",
            )

            r = http.patch(
                f"{API_BASE}/videos/{legacy_patch_id}",
                headers=headers_other,
                json={"thumbnail_url": "should-not-save.jpg"},
            )
            body = detail(r)
            record(
                "PATCH legacy missing uploader_id as non-admin is denied",
                r.status_code == 403 and "Not your video" in json.dumps(body),
                r,
                "403 Not your video, not 500",
            )

            r = http.patch(
                f"{API_BASE}/videos/{normal_id}",
                headers=headers_admin,
                json={"thumbnail_url": "normal-admin-thumb.jpg"},
            )
            body = detail(r)
            record(
                "PATCH normal doc as admin changes thumbnail",
                r.status_code == 200 and isinstance(body, dict) and body.get("thumbnail_url") == "normal-admin-thumb.jpg",
                r,
                "200 with thumbnail_url=normal-admin-thumb.jpg",
            )

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
                "403 Not your video, not 500",
            )

            # Regression for normal owner editing.
            r = http.patch(
                f"{API_BASE}/videos/{normal_id}",
                headers=headers_owner,
                json={"thumbnail_url": "normal-new-thumb.jpg"},
            )
            body = detail(r)
            record(
                "PATCH normal doc as non-admin owner changes thumbnail",
                r.status_code == 200 and isinstance(body, dict) and body.get("thumbnail_url") == "normal-new-thumb.jpg",
                r,
                "200 with thumbnail_url=normal-new-thumb.jpg",
            )

            # User's remaining subtitle-upload symptom, using .vtt to avoid ffmpeg dependency.
            files = {"file": ("caption.vtt", b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n", "text/vtt")}
            data = {"language": "en", "label": "English"}
            r = http.post(f"{API_BASE}/videos/{legacy_post_id}/subtitles", headers=headers_admin, files=files, data=data)
            body = detail(r)
            db_after_post = db.videos.find_one({"id": legacy_post_id}, {"_id": 0, "subtitles": 1}) or {}
            record(
                "POST subtitle .vtt to legacy missing uploader_id as admin returns subtitle object",
                r.status_code == 200
                and isinstance(body, dict)
                and body.get("id")
                and body.get("url")
                and body.get("language") == "en"
                and len(db_after_post.get("subtitles", [])) == 1
                and "uploader_id" not in json.dumps(body),
                r,
                "200 subtitle object persisted, no uploader_id KeyError",
            )

            files = {"file": ("blocked.vtt", b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nBlocked\n", "text/vtt")}
            r = http.post(f"{API_BASE}/videos/{legacy_post_id}/subtitles", headers=headers_other, files=files, data=data)
            body = detail(r)
            record(
                "POST subtitle to legacy missing uploader_id as non-admin is denied",
                r.status_code == 403 and "Not your video" in json.dumps(body),
                r,
                "403 Not your video, not 500",
            )

            r = http.delete(f"{API_BASE}/videos/{legacy_delete_nonadmin_id}", headers=headers_other)
            body = detail(r)
            still_exists = db.videos.find_one({"id": legacy_delete_nonadmin_id}, {"_id": 0, "id": 1}) is not None
            record(
                "DELETE legacy missing uploader_id video as non-admin is denied",
                r.status_code == 403 and "Not yours" in json.dumps(body) and still_exists,
                r,
                "403 Not yours and video remains",
            )

            r = http.delete(f"{API_BASE}/videos/{legacy_delete_admin_id}", headers=headers_admin)
            body = detail(r)
            deleted = db.videos.find_one({"id": legacy_delete_admin_id}, {"_id": 0, "id": 1}) is None
            record(
                "DELETE legacy missing uploader_id video as admin succeeds",
                r.status_code == 200 and isinstance(body, dict) and body.get("ok") is True and deleted,
                r,
                "200 ok and video removed, no KeyError",
            )

            r = http.delete(f"{API_BASE}/videos/{legacy_delete_sub_id}/subtitles/{existing_sub_id}", headers=headers_admin)
            body = detail(r)
            after_delete_sub = db.videos.find_one({"id": legacy_delete_sub_id}, {"_id": 0, "subtitles": 1}) or {}
            sub_removed = all(s.get("id") != existing_sub_id for s in after_delete_sub.get("subtitles", []))
            record(
                "DELETE subtitle on legacy missing uploader_id video as admin succeeds",
                r.status_code == 200 and isinstance(body, dict) and body.get("ok") is True and sub_removed,
                r,
                "200 ok and subtitle pulled, no KeyError",
            )

        print("\nRESULT_JSON_START")
        print(json.dumps({"run_id": RUN_ID, "api_base": API_BASE, "results": results}, indent=2, default=str))
        print("RESULT_JSON_END")
        return 0 if all(r["passed"] for r in results) else 1
    finally:
        if seeded_video_ids:
            db.videos.delete_many({"id": {"$in": seeded_video_ids}})
        if seeded_user_ids:
            db.users.delete_many({"id": {"$in": seeded_user_ids}})
        for path in (UPLOAD_DIR / "subtitles").glob(f"*{RUN_ID}*"):
            try:
                path.unlink()
            except Exception:
                pass
        client.close()


if __name__ == "__main__":
    sys.exit(main())