#!/usr/bin/env python3
"""Focused regression test for PRO/VIP expiry sweeper.

This script intentionally seeds only disposable users whose email starts with
bug-expiry-qa- and removes them at the end.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient


BACKEND_ENV = dotenv_values("/app/backend/.env")
MONGO_URL = BACKEND_ENV.get("MONGO_URL") or os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
DB_NAME = BACKEND_ENV.get("DB_NAME") or os.environ.get("DB_NAME") or "test_database"
API_BASE = os.environ.get("API_BASE", "http://localhost:8001/api")
ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASSWORD = "Admin123!"


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def user_doc(prefix: str, slug: str, **overrides):
    now = iso(datetime.now(timezone.utc))
    doc = {
        "id": f"{prefix}-{slug}",
        "email": f"{prefix}-{slug}@example.com",
        "username": f"{prefix}_{slug}",
        "password_hash": "not-used-in-this-test",
        "role": "user",
        "is_pro": False,
        "pro_package_id": None,
        "pro_expires_at": None,
        "is_vip": False,
        "vip_package_id": None,
        "vip_expires_at": None,
        "email_verified": True,
        "verify_token": None,
        "avatar_url": None,
        "cover_url": None,
        "bio": None,
        "banned_until": None,
        "banned_reason": None,
        "chat_banned_until": None,
        "chat_banned_reason": None,
        "coins": 0,
        "owned_frames": [],
        "selected_frame_id": None,
        "created_at": now,
    }
    doc.update(overrides)
    return doc


async def wait_for_api(timeout_s: int = 60) -> None:
    deadline = time.time() + timeout_s
    last_error = None
    async with httpx.AsyncClient(timeout=5) as client:
        while time.time() < deadline:
            try:
                resp = await client.get(f"{API_BASE}/")
                if resp.status_code == 200:
                    return
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as exc:  # noqa: BLE001
                last_error = repr(exc)
            await asyncio.sleep(1)
    raise AssertionError(f"API did not become healthy within {timeout_s}s; last_error={last_error}")


async def login_admin() -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{API_BASE}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
    assert resp.status_code == 200, f"admin login failed: {resp.status_code} {resp.text}"
    token = resp.json().get("token")
    assert token, "admin login response did not include token"
    return token


async def admin_get_users(token: str, q: str, limit: int = 200):
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{API_BASE}/admin/users", headers=headers, params={"q": q, "limit": limit})
    assert resp.status_code == 200, f"GET /admin/users failed: {resp.status_code} {resp.text}"
    body = resp.json()
    return body["items"]


async def admin_post(token: str, path: str, payload: dict):
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{API_BASE}{path}", headers=headers, json=payload)
    assert resp.status_code == 200, f"POST {path} failed: {resp.status_code} {resp.text}"
    return resp.json()


async def main() -> dict:
    prefix = f"bug-expiry-qa-{uuid4().hex[:8]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    results = {"prefix": prefix, "checks": []}
    now = datetime.now(timezone.utc)
    past_iso = iso(now - timedelta(days=2))
    future_iso = iso(now + timedelta(days=30))
    july31_date_only = "2026-07-31"

    async def cleanup():
        await db.users.delete_many({"email": {"$regex": f"^{prefix}"}})

    try:
        await cleanup()

        # Startup sweep proof: seed stale users before backend restart.
        startup_docs = [
            user_doc(prefix, "startup-expired-pro", is_pro=True, pro_expires_at=past_iso),
            user_doc(prefix, "startup-expired-vip", is_vip=True, vip_expires_at=past_iso),
        ]
        await db.users.insert_many(startup_docs)
        restart = subprocess.run(
            ["sudo", "supervisorctl", "restart", "backend"],
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        results["supervisor_restart"] = {
            "returncode": restart.returncode,
            "stdout": restart.stdout.strip(),
            "stderr": restart.stderr.strip(),
        }
        assert restart.returncode == 0, f"backend restart failed: {results['supervisor_restart']}"
        await wait_for_api()
        startup_after = await db.users.find({"id": {"$in": [d["id"] for d in startup_docs]}}, {"_id": 0}).to_list(10)
        startup_by_id = {u["id"]: u for u in startup_after}
        assert startup_by_id[f"{prefix}-startup-expired-pro"]["is_pro"] is False, startup_by_id
        assert startup_by_id[f"{prefix}-startup-expired-vip"]["is_vip"] is False, startup_by_id
        results["checks"].append("startup sweep flips stale PRO/VIP flags in DB after supervisor restart")

        token = await login_admin()
        results["checks"].append("admin login succeeded")

        # Admin list sweep proof and edge cases.
        admin_docs = [
            user_doc(prefix, "expired-pro", is_pro=True, pro_expires_at=past_iso),
            user_doc(prefix, "expired-pro-date-only", is_pro=True, pro_expires_at=july31_date_only),
            user_doc(prefix, "future-pro", is_pro=True, pro_expires_at=future_iso),
            user_doc(prefix, "permanent-pro", is_pro=True, pro_expires_at="permanent"),
            user_doc(prefix, "null-pro", is_pro=True, pro_expires_at=None),
            user_doc(prefix, "missing-pro", is_pro=True),
            user_doc(prefix, "expired-vip", is_vip=True, vip_expires_at=past_iso),
            user_doc(prefix, "future-vip", is_vip=True, vip_expires_at=future_iso),
            user_doc(prefix, "permanent-vip", is_vip=True, vip_expires_at="permanent"),
            user_doc(prefix, "null-vip", is_vip=True, vip_expires_at=None),
        ]
        del admin_docs[5]["pro_expires_at"]
        await db.users.insert_many(admin_docs)
        before = await db.users.find({"email": {"$regex": f"^{prefix}"}}, {"_id": 0}).to_list(50)
        results["seeded_before_admin_list_count"] = len(before)

        items = await admin_get_users(token, prefix)
        by_id = {u["id"]: u for u in items}
        expected_ids = {d["id"] for d in startup_docs + admin_docs}
        missing = expected_ids - set(by_id)
        assert not missing, f"admin list did not return seeded users: {missing}"

        assert by_id[f"{prefix}-expired-pro"]["is_pro"] is False, by_id[f"{prefix}-expired-pro"]
        assert by_id[f"{prefix}-expired-pro-date-only"]["is_pro"] is False, by_id[f"{prefix}-expired-pro-date-only"]
        assert by_id[f"{prefix}-expired-vip"]["is_vip"] is False, by_id[f"{prefix}-expired-vip"]
        for slug in ["future-pro", "permanent-pro", "null-pro", "missing-pro"]:
            assert by_id[f"{prefix}-{slug}"]["is_pro"] is True, by_id[f"{prefix}-{slug}"]
        for slug in ["future-vip", "permanent-vip", "null-vip"]:
            assert by_id[f"{prefix}-{slug}"]["is_vip"] is True, by_id[f"{prefix}-{slug}"]
        results["checks"].append("GET /api/admin/users response contains no stale active PRO/VIP and preserves future/permanent/null/missing cases")

        db_after = await db.users.find({"id": {"$in": list(expected_ids)}}, {"_id": 0}).to_list(50)
        db_by_id = {u["id"]: u for u in db_after}
        assert db_by_id[f"{prefix}-expired-pro"]["is_pro"] is False, db_by_id[f"{prefix}-expired-pro"]
        assert db_by_id[f"{prefix}-expired-pro-date-only"]["is_pro"] is False, db_by_id[f"{prefix}-expired-pro-date-only"]
        assert db_by_id[f"{prefix}-expired-vip"]["is_vip"] is False, db_by_id[f"{prefix}-expired-vip"]
        results["checks"].append("admin-list sweep persisted expired PRO/VIP flag changes to MongoDB")

        # Idempotency: second admin list call should not break preserved cases.
        second_items = await admin_get_users(token, prefix)
        second_by_id = {u["id"]: u for u in second_items}
        assert second_by_id[f"{prefix}-future-pro"]["is_pro"] is True
        assert second_by_id[f"{prefix}-permanent-pro"]["is_pro"] is True
        assert second_by_id[f"{prefix}-future-vip"]["is_vip"] is True
        assert second_by_id[f"{prefix}-permanent-vip"]["is_vip"] is True
        results["checks"].append("sweeper/admin listing is idempotent")

        # Grant endpoint regression checks.
        grant_future = user_doc(prefix, "grant-future")
        grant_perm = user_doc(prefix, "grant-permanent")
        await db.users.insert_many([grant_future, grant_perm])

        grant_pro_resp = await admin_post(token, f"/admin/users/{grant_future['id']}/grant-pro", {"duration": "1day"})
        grant_vip_resp = await admin_post(token, f"/admin/users/{grant_future['id']}/grant-vip", {"duration": "1day"})
        grant_future_db = await db.users.find_one({"id": grant_future["id"]}, {"_id": 0})
        assert grant_future_db["is_pro"] is True and grant_future_db["pro_expires_at"] == grant_pro_resp["pro_expires_at"]
        assert grant_future_db["is_vip"] is True and grant_future_db["vip_expires_at"] == grant_vip_resp["vip_expires_at"]
        assert grant_future_db["pro_expires_at"] > iso(datetime.now(timezone.utc))
        assert grant_future_db["vip_expires_at"] > iso(datetime.now(timezone.utc))

        await admin_post(token, f"/admin/users/{grant_perm['id']}/grant-pro", {"duration": "permanent"})
        await admin_post(token, f"/admin/users/{grant_perm['id']}/grant-vip", {"duration": "permanent"})
        _ = await admin_get_users(token, prefix)
        grant_perm_db = await db.users.find_one({"id": grant_perm["id"]}, {"_id": 0})
        assert grant_perm_db["is_pro"] is True and grant_perm_db["pro_expires_at"] == "permanent", grant_perm_db
        assert grant_perm_db["is_vip"] is True and grant_perm_db["vip_expires_at"] == "permanent", grant_perm_db
        results["checks"].append("grant-pro/grant-vip future and permanent durations remain active after sweeper")

        # Capture the relevant startup log if present; DB assertions above are authoritative.
        log_probe = subprocess.run(
            "grep -F '[startup] expired' /var/log/supervisor/backend*.log | tail -n 5",
            shell=True,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        results["startup_log_probe"] = log_probe.stdout.strip().splitlines()
        return results
    finally:
        try:
            await cleanup()
        finally:
            client.close()


if __name__ == "__main__":
    try:
        outcome = asyncio.run(main())
        print(json.dumps({"status": "passed", **outcome}, indent=2, sort_keys=True))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error": repr(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        raise