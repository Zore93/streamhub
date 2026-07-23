#!/usr/bin/env python3
"""Iteration 14 focused backend verification for thumbnail save + subtitle upload regression.

Seeds one legacy MongoDB video document without a synopsis field and exercises only
the affected API endpoints through the configured preview/backend URL.
"""
from __future__ import annotations

import json
import os
import shutil
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
UPLOAD_DIR = Path(BACKEND_ENV.get("UPLOAD_DIR") or "/app/uploads")


def record(results: list[dict[str, Any]], name: str, passed: bool, **details: Any) -> None:
    results.append({"name": name, "passed": passed, **details})
    mark = "PASS" if passed else "FAIL"
    print(f"{mark}: {name} :: {json.dumps(details, default=str, ensure_ascii=False)}")


def json_body(resp: requests.Response) -> dict[str, Any]:
    if resp.headers.get("content-type", "").startswith("application/json"):
        return resp.json()
    return {}


def cleanup_uploads(video_id: str) -> None:
    sub_dir = UPLOAD_DIR / "subtitles"
    if not sub_dir.exists():
        return
    for path in sub_dir.glob(f"{video_id}_*"):
        try:
            path.unlink()
        except Exception as exc:  # noqa: BLE001
            print(f"cleanup upload warning for {path}: {exc}")


def main() -> int:
    results: list[dict[str, Any]] = []
    session = requests.Session()
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    video_id = f"qa-legacy-no-synopsis-it14-{int(time.time())}"
    sub_id: str | None = None

    try:
        ffmpeg_path = shutil.which("ffmpeg")
        record(results, "environment has ffmpeg missing for .srt negative-path check", ffmpeg_path is None, ffmpeg_path=ffmpeg_path)

        login = session.post(
            f"{API}/auth/login",
            json={"email": "admin@streamhub.io", "password": "Admin123!"},
            timeout=20,
        )
        record(results, "admin login", login.status_code == 200, status=login.status_code, body=login.text[:300])
        if login.status_code != 200:
            return 2
        payload = login.json()
        headers = {"Authorization": f"Bearer {payload['token']}"}
        admin = payload["user"]

        seed_doc = {
            "id": video_id,
            "title": "QA legacy video without synopsis iteration 14",
            "slug": video_id,
            "description": "Seeded by iteration 14 bug verification script",
            # Intentionally omit synopsis to mimic legacy/migrated records.
            "tags": ["qa", "regression"],
            "uploader_id": admin["id"],
            "uploader_username": admin["username"],
            "thumbnail_url": "thumbnails/qa-it14-thumb-a.jpg",
            "thumbnail_options": ["thumbnails/qa-it14-thumb-a.jpg", "thumbnails/qa-it14-thumb-b.jpg"],
            "duration_sec": 12.0,
            "original_filename": "qa-it14.mp4",
            "original_size_bytes": 1234,
            "original_width": 640,
            "original_height": 360,
            "status": "ready",
            "progress": 100,
            "error": None,
            "renditions": [{"resolution": "360p", "url": "videos/qa-it14.mp4", "width": 640, "height": 360}],
            "subtitles": [],
            "access_tier": "free",
            "is_short": False,
            "views": 0,
            "likes": [],
            "created_at": "2026-07-01T00:00:00+00:00",
        }
        db.videos.delete_many({"id": video_id})
        db.videos.insert_one(seed_doc)
        record(results, "seed legacy video without synopsis", True, video_id=video_id)

        get_resp = session.get(f"{API}/videos/{video_id}", headers=headers, timeout=20)
        get_json = json_body(get_resp)
        record(
            results,
            "GET /videos/{id} returns synopsis empty string for legacy doc",
            get_resp.status_code == 200 and get_json.get("synopsis") == "",
            status=get_resp.status_code,
            has_synopsis="synopsis" in get_json,
            synopsis_value=get_json.get("synopsis"),
            body=get_resp.text[:300],
        )

        patch_resp = session.patch(
            f"{API}/videos/{video_id}",
            headers=headers,
            json={"thumbnail_url": "thumbnails/qa-it14-thumb-b.jpg"},
            timeout=20,
        )
        patch_json = json_body(patch_resp)
        persisted = db.videos.find_one({"id": video_id}, {"_id": 0}) or {}
        record(
            results,
            "PATCH thumbnail_url on legacy doc returns 200 with synopsis empty string",
            patch_resp.status_code == 200
            and patch_json.get("thumbnail_url") == "thumbnails/qa-it14-thumb-b.jpg"
            and persisted.get("thumbnail_url") == "thumbnails/qa-it14-thumb-b.jpg"
            and patch_json.get("synopsis") == "",
            status=patch_resp.status_code,
            response_thumbnail=patch_json.get("thumbnail_url"),
            persisted_thumbnail=persisted.get("thumbnail_url"),
            has_synopsis="synopsis" in patch_json,
            synopsis_value=patch_json.get("synopsis"),
            body=patch_resp.text[:500],
        )

        patch_same_resp = session.patch(
            f"{API}/videos/{video_id}",
            headers=headers,
            json={"thumbnail_url": "thumbnails/qa-it14-thumb-b.jpg"},
            timeout=20,
        )
        patch_same_json = json_body(patch_same_resp)
        record(
            results,
            "PATCH thumbnail_url with existing value still returns 200",
            patch_same_resp.status_code == 200 and patch_same_json.get("thumbnail_url") == "thumbnails/qa-it14-thumb-b.jpg",
            status=patch_same_resp.status_code,
            body=patch_same_resp.text[:300],
        )

        srt = "1\n00:00:00,000 --> 00:00:01,000\nQA subtitle line\n"
        srt_resp = session.post(
            f"{API}/videos/{video_id}/subtitles",
            headers=headers,
            data={"language": "en", "label": "English SRT QA"},
            files={"file": ("qa.en.srt", srt.encode("utf-8"), "application/x-subrip")},
            timeout=40,
        )
        srt_json = json_body(srt_resp)
        srt_detail = srt_json.get("detail")
        record(
            results,
            "POST .srt subtitle with missing ffmpeg returns JSON 500 detail mentioning ffmpeg not installed",
            srt_resp.status_code == 500
            and isinstance(srt_detail, str)
            and "ffmpeg" in srt_detail.lower()
            and "not installed" in srt_detail.lower(),
            status=srt_resp.status_code,
            content_type=srt_resp.headers.get("content-type"),
            detail=srt_detail,
            body=srt_resp.text[:600],
        )

        vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nQA VTT subtitle line\n"
        vtt_resp = session.post(
            f"{API}/videos/{video_id}/subtitles",
            headers=headers,
            data={"language": "en", "label": "English VTT QA"},
            files={"file": ("qa.en.vtt", vtt.encode("utf-8"), "text/vtt")},
            timeout=40,
        )
        vtt_json = json_body(vtt_resp)
        sub_id = vtt_json.get("id")
        record(
            results,
            "POST .vtt subtitle bypasses ffmpeg and returns subtitle object",
            vtt_resp.status_code == 200
            and bool(sub_id)
            and vtt_json.get("language") == "en"
            and vtt_json.get("label") == "English VTT QA"
            and str(vtt_json.get("url", "")).endswith(".vtt"),
            status=vtt_resp.status_code,
            subtitle=vtt_json,
            body=vtt_resp.text[:600],
        )

        delete_resp = session.delete(f"{API}/videos/{video_id}/subtitles/{sub_id}", headers=headers, timeout=20) if sub_id else None
        delete_json = json_body(delete_resp) if delete_resp else {}
        record(
            results,
            "DELETE existing subtitle returns 200",
            bool(delete_resp) and delete_resp.status_code == 200 and delete_json.get("ok") is True,
            status=getattr(delete_resp, "status_code", None),
            body=(delete_resp.text[:300] if delete_resp else "no subtitle id from .vtt upload"),
        )

    finally:
        try:
            db.videos.delete_many({"id": video_id})
            cleanup_uploads(video_id)
        except Exception as exc:  # noqa: BLE001
            print(f"cleanup warning: {exc}")
        client.close()

    passed = sum(1 for result in results if result["passed"])
    summary = {"passed": passed, "total": len(results), "results": results}
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())