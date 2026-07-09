from __future__ import annotations

import io
import os
import time
import uuid
import zipfile

import pytest
import requests
from PIL import Image, ImageDraw


BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT_SECONDS = int(os.getenv("E2E_TIMEOUT_SECONDS", "180"))
PASSWORD = "E2e-password-123"


def _url(path_or_url: str) -> str:
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    return f"{BASE_URL}{path_or_url}"


def _request(method: str, path: str, session: requests.Session | None = None, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", 30)
    client = session or requests
    return client.request(method, _url(path), **kwargs)


def _sample_product_png() -> bytes:
    image = Image.new("RGBA", (320, 320), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((82, 64, 238, 250), radius=34, fill=(37, 99, 235, 255))
    draw.rounded_rectangle((112, 42, 208, 92), radius=18, fill=(96, 165, 250, 255))
    draw.ellipse((126, 112, 194, 180), fill=(219, 234, 254, 255))
    draw.rectangle((112, 214, 208, 238), fill=(30, 64, 175, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _register_user(label: str) -> tuple[requests.Session, dict]:
    email = f"e2e-{label}-{uuid.uuid4().hex}@example.test"
    session = requests.Session()
    response = _request(
        "POST",
        "/api/auth/register",
        session=session,
        json={"email": email, "password": PASSWORD, "display_name": f"E2E {label}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["user"]["email"] == email

    session.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return session, data["user"]


def _poll_task(task_id: str, session: requests.Session) -> dict:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_task: dict | None = None

    while time.monotonic() < deadline:
        response = _request("GET", f"/api/tasks/{task_id}", session=session)
        assert response.status_code == 200, response.text
        last_task = response.json()
        assert 0 <= last_task["progress"] <= 100
        assert last_task["status"] in {"queued", "processing", "success", "failed"}
        if last_task["status"] in {"success", "failed"}:
            return last_task
        time.sleep(1.5)

    pytest.fail(f"Task {task_id} did not finish in {TIMEOUT_SECONDS}s; last={last_task}")


def test_frontend_shell_and_core_api_are_available() -> None:
    page = _request("GET", "/")
    assert page.status_code == 200
    assert "ProductShot AI" in page.text
    assert "auth.js" in page.text
    assert "async-polling.js" in page.text
    assert "ui-polish.js" in page.text

    health = _request("GET", "/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    templates = _request("GET", "/api/templates")
    assert templates.status_code == 200
    template_ids = {template["id"] for template in templates.json()}
    assert {"amazon-white-main", "transparent-png", "soft-shadow-packshot"} <= template_ids


def test_auth_required_register_login_and_duplicate_guard() -> None:
    unauthorized = _request("GET", "/api/history?limit=1")
    assert unauthorized.status_code == 401

    upload_without_auth = _request(
        "POST",
        "/api/upload",
        files={"file": ("e2e-product.png", _sample_product_png(), "image/png")},
    )
    assert upload_without_auth.status_code == 401

    session, user = _register_user("auth")

    me = _request("GET", "/api/auth/me", session=session)
    assert me.status_code == 200
    assert me.json()["id"] == user["id"]

    duplicate = _request(
        "POST",
        "/api/auth/register",
        json={"email": user["email"], "password": PASSWORD, "display_name": "Duplicate"},
    )
    assert duplicate.status_code == 409

    cookie_session = requests.Session()
    login = _request(
        "POST",
        "/api/auth/login",
        session=cookie_session,
        json={"email": user["email"].upper(), "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["id"] == user["id"]

    cookie_me = _request("GET", "/api/auth/me", session=cookie_session)
    assert cookie_me.status_code == 200
    assert cookie_me.json()["id"] == user["id"]

    logout = _request("POST", "/api/auth/logout", session=cookie_session)
    assert logout.status_code == 200
    assert logout.json()["ok"] is True

    logged_out_me = _request("GET", "/api/auth/me", session=cookie_session)
    assert logged_out_me.status_code == 401


def test_upload_async_generate_download_history_retry_guard_and_user_isolation() -> None:
    owner_session, _owner = _register_user("owner")
    other_session, _other = _register_user("other")

    uploaded = _request(
        "POST",
        "/api/upload",
        session=owner_session,
        files={"file": ("e2e-product.png", _sample_product_png(), "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    source = uploaded.json()
    assert source["id"]
    assert source["width"] == 320
    assert source["height"] == 320
    assert "/api/source-images/" in source["public_url"]
    assert "expires=" in source["public_url"]
    assert "sig=" in source["public_url"]
    source_image = _request("GET", source["public_url"])
    assert source_image.status_code == 200
    assert source_image.content.startswith(b"\x89PNG")

    isolated_generate = _request(
        "POST",
        "/api/generate",
        session=other_session,
        json={
            "source_image_id": source["id"],
            "template_id": "transparent-png",
            "width": 512,
            "height": 512,
            "product_fill_ratio": 0.78,
            "background": "transparent",
            "add_shadow": False,
            "auto_enhance": False,
            "edge_repair": False,
            "sharpen": False,
            "output_format": "png",
        },
    )
    assert isolated_generate.status_code == 404

    generated = _request(
        "POST",
        "/api/generate",
        session=owner_session,
        json={
            "source_image_id": source["id"],
            "template_id": "transparent-png",
            "width": 512,
            "height": 512,
            "product_fill_ratio": 0.78,
            "background": "transparent",
            "add_shadow": False,
            "auto_enhance": False,
            "edge_repair": False,
            "sharpen": False,
            "output_format": "png",
        },
    )
    assert generated.status_code == 200, generated.text
    queued_task = generated.json()
    assert queued_task["id"]
    assert queued_task["source_image_id"] == source["id"]
    assert queued_task["status"] in {"queued", "processing", "success"}

    task_id = queued_task["id"]
    try:
        other_task = _request("GET", f"/api/tasks/{task_id}", session=other_session)
        assert other_task.status_code == 404

        final_task = _poll_task(task_id, owner_session)
        assert final_task["status"] == "success", final_task.get("error_message")
        assert final_task["progress"] == 100
        assert final_task["compliance_score"] is not None
        assert len(final_task["assets"]) >= 2

        for asset in final_task["assets"]:
            assert "/api/assets/" in asset["public_url"]
            assert "expires=" in asset["public_url"]
            assert "sig=" in asset["public_url"]
            asset_response = _request("GET", asset["public_url"])
            assert asset_response.status_code == 200
            assert asset_response.content.startswith(b"\x89PNG")

        other_archive = _request("GET", f"/api/tasks/{task_id}/download.zip", session=other_session)
        assert other_archive.status_code == 404

        archive = _request("GET", f"/api/tasks/{task_id}/download.zip", session=owner_session)
        assert archive.status_code == 200
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zip_file:
            names = zip_file.namelist()
        assert any(name.endswith(".png") for name in names)

        history = _request("GET", "/api/history?limit=20", session=owner_session)
        assert history.status_code == 200
        assert task_id in {task["id"] for task in history.json()["tasks"]}

        other_history = _request("GET", "/api/history?limit=20", session=other_session)
        assert other_history.status_code == 200
        assert task_id not in {task["id"] for task in other_history.json()["tasks"]}

        retry = _request("POST", f"/api/tasks/{task_id}/retry", session=owner_session)
        assert retry.status_code == 400
    finally:
        _request("DELETE", f"/api/tasks/{task_id}", session=owner_session)
