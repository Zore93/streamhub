#!/usr/bin/env python3
"""Focused backend verification for thumbnail PATCH and subtitle upload regression.

This script seeds one migrated-style video document without a synopsis field,
then exercises the affected API endpoints through the preview ingress.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import dotenv_values
from pymongo import MongoClient


APP = Path("/app")
FRONTEND_ENV = dotenv_values(APP / "frontend" / ".env")
BACKEND_ENV = dotenv_values(APP / "backend" / ".env")
BASE = (FRONTEND_ENV.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"
MONGO_URL = BACKEND_ENV.get("MONGO_URL") or os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
DB_NAME = BACKEND_ENV.get("DB_NAME") or os.environ.get("DB_NAME") or "test_database"


def record(results: list[dict[str, Any]], name: str, passed: bool, **details: Any) -> None:
    results.append({"name": name, "passed": passed, **details})
    mark = "PASS" if passed else "FAIL"
    print(f"{mark}: {name} :: {json.dumps(details, default=str, ensure_ascii=False)}")


def main() -> int:
    results: list[dict[str, Any]] = []
    session = requests.Session()
    session.timeout = 20
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    video_id = f"qa-migrated-no-synopsis-{int(time.time())}"
    token = None
    sub_id = None

    try:
        login = session.post(
            f"{API}/auth/login",
            json={"email": "admin@streamhub.io", "password": "Admin123!"},
            timeout=20,
        )
        record(results, "admin login", login.status_code == 200, status=login.status_code, body=login.text[:300])
        if login.status_code != 200:
            return 2
        payload = login.json()
        token = payload["token"]
        admin = payload["user"]
        headers = {"Authorization": f"Bearer {token}"}

        seed_doc = {
            "id": video_id,
            "title": "QA migrated video without synopsis",
            "slug": video_id,
            "description": "Seeded by bug verification script",
            # Intentionally omit synopsis to mimic migrated MongoDB records.
            "tags": ["qa", "regression"],
            "uploader_id": admin["id"],
            "uploader_username": admin["username"],
            "thumbnail_url": "thumbnails/qa-thumb-a.jpg",
            "thumbnail_options": ["thumbnails/qa-thumb-a.jpg", "thumbnails/qa-thumb-b.jpg"],
            "duration_sec": 12.0,
            "original_filename": "qa.mp4",
            "original_size_bytes": 1234,
            "original_width": 640,
            "original_height": 360,
            "status": "ready",
            "progress": 100,
            "error": None,
            "renditions": [{"resolution": "360p", "url": "videos/qa.mp4", "width": 640, "height": 360}],
            "subtitles": [],
            "access_tier": "free",
            "is_short": False,
            "views": 0,
            "likes": [],
            "created_at": "2026-07-01T00:00:00+00:00",
        }
        db.videos.delete_many({"id": video_id})
        db.videos.insert_one(seed_doc)
        record(results, "seed migrated video without synopsis", True, video_id=video_id)

        get_resp = session.get(f"{API}/videos/{video_id}", headers=headers, timeout=20)
        get_json = get_resp.json() if get_resp.headers.get("content-type", "").startswith("application/json") else {}
        record(
            results,
            "GET /videos/{id} includes default synopsis for old docs",
            get_resp.status_code == 200 and get_json.get("synopsis") == "",
            status=get_resp.status_code,
            has_synopsis="synopsis" in get_json,
            synopsis_value=get_json.get("synopsis"),
        )

        patch_resp = session.patch(
            f"{API}/videos/{video_id}",
            headers=headers,
            json={"thumbnail_url": "thumbnails/qa-thumb-b.jpg"},
            timeout=20,
        )
        patch_json = patch_resp.json() if patch_resp.headers.get("content-type", "").startswith("application/json") else {}
        persisted = db.videos.find_one({"id": video_id}, {"_id": 0}) or {}
        record(
            results,
            "PATCH thumbnail_url returns 200 and persists updated thumbnail",
            patch_resp.status_code == 200
            and patch_json.get("thumbnail_url") == "thumbnails/qa-thumb-b.jpg"
            and persisted.get("thumbnail_url") == "thumbnails/qa-thumb-b.jpg",
            status=patch_resp.status_code,
            response_thumbnail=patch_json.get("thumbnail_url"),
            persisted_thumbnail=persisted.get("thumbnail_url"),
            body=patch_resp.text[:300],
        )

        invalid_resp = session.patch(
            f"{API}/videos/{video_id}",
            headers=headers,
            json={"synopsis": {"not": "a string"}},
            timeout=20,
        )
        invalid_body = invalid_resp.json() if invalid_resp.headers.get("content-type", "").startswith("application/json") else {}
        invalid_detail = invalid_body.get("detail")
        record(
            results,
            "PATCH invalid synopsis type returns descriptive Update failed detail",
            invalid_resp.status_code == 500
            and isinstance(invalid_detail, str)
            and invalid_detail.startswith("Update failed:")
            and ":" in invalid_detail[len("Update failed:") :],
            status=invalid_resp.status_code,
            detail=invalid_detail,
            body=invalid_resp.text[:600],
        )

        srt = "1\n00:00:00,000 --> 00:00:01,000\nQA subtitle line\n"
        files = {"file": ("qa.en.srt", srt.encode("utf-8"), "application/x-subrip")}
        sub_resp = session.post(
            f"{API}/videos/{video_id}/subtitles",
            headers=headers,
            data={"language": "en", "label": "English QA"},
            files=files,
            timeout=40,
        )
        sub_json = sub_resp.json() if sub_resp.headers.get("content-type", "").startswith("application/json") else {}
        sub_id = sub_json.get("id")
        record(
            results,
            "POST valid .srt subtitle returns subtitle dict",
            sub_resp.status_code == 200
            and bool(sub_id)
            and sub_json.get("language") == "en"
            and sub_json.get("label") == "English QA"
            and sub_json.get("url", "").endswith(".vtt"),
            status=sub_resp.status_code,
            subtitle=sub_json,
            body=sub_resp.text[:600],
        )

        if not sub_id:
            sub_id = "qa-seeded-delete-subtitle"
            db.videos.update_one(
                {"id": video_id},
                {"$push": {"subtitles": {
                    "id": sub_id,
                    "language": "en",
                    "label": "Seeded delete check",
                    "url": "subtitles/nonexistent-delete-check.vtt",
                    "original_url": None,
                    "format": "vtt",
                    "created_at": "2026-07-01T00:00:00+00:00",
                }}},
            )

        delete_valid = session.delete(f"{API}/videos/{video_id}/subtitles/{sub_id}", headers=headers, timeout=20) if sub_id else None
        delete_valid_json = delete_valid.json() if delete_valid and delete_valid.headers.get("content-type", "").startswith("application/json") else {}
        record(
            results,
            "DELETE existing subtitle returns 200",
            bool(delete_valid) and delete_valid.status_code == 200 and delete_valid_json.get("ok") is True,
            status=getattr(delete_valid, "status_code", None),
            body=(delete_valid.text[:300] if delete_valid else "no subtitle id"),
        )

        delete_unknown = session.delete(f"{API}/videos/{video_id}/subtitles/unknown-sub-id", headers=headers, timeout=20)
        delete_unknown_json = delete_unknown.json() if delete_unknown.headers.get("content-type", "").startswith("application/json") else {}
        record(
            results,
            "DELETE unknown subtitle returns 404",
            delete_unknown.status_code == 404 and delete_unknown_json.get("detail") == "Subtitle not found",
            status=delete_unknown.status_code,
            detail=delete_unknown_json.get("detail"),
            body=delete_unknown.text[:300],
        )

    finally:
        try:
            db.videos.delete_many({"id": video_id})
        except Exception as exc:  # noqa: BLE001
            print(f"cleanup warning: {exc}")
        client.close()

    passed = sum(1 for r in results if r["passed"])
    print(json.dumps({"passed": passed, "total": len(results), "results": results}, indent=2, ensure_ascii=False, default=str))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())