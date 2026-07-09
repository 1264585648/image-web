from __future__ import annotations

import io
import os
import time
import zipfile

import pytest
import requests
from PIL import Image, ImageDraw


BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT_SECONDS = int(os.getenv("E2E_TIMEOUT_SECONDS", "180"))


def _request(method: str, path: str, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", 30)
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


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


def _poll_task(task_id: str) -> dict:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_task: dict | None = None

    while time.monotonic() < deadline:
        response = _request("GET", f"/api/tasks/{task_id}")
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
    assert "async-polling.js" in page.text

    health = _request("GET", "/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    templates = _request("GET", "/api/templates")
    assert templates.status_code == 200
    template_ids = {template["id"] for template in templates.json()}
    assert {"amazon-white-main", "transparent-png", "soft-shadow-packshot"} <= template_ids


def test_upload_async_generate_download_history_and_retry_guard() -> None:
    uploaded = _request(
        "POST",
        "/api/upload",
        files={"file": ("e2e-product.png", _sample_product_png(), "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    source = uploaded.json()
    assert source["id"]
    assert source["width"] == 320
    assert source["height"] == 320
    assert source["public_url"].startswith(BASE_URL)

    generated = _request(
        "POST",
        "/api/generate",
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
        final_task = _poll_task(task_id)
        assert final_task["status"] == "success", final_task.get("error_message")
        assert final_task["progress"] == 100
        assert final_task["compliance_score"] is not None
        assert len(final_task["assets"]) >= 2

        for asset in final_task["assets"]:
            assert asset["public_url"].startswith(BASE_URL)
            asset_response = _request("GET", asset["public_url"].removeprefix(BASE_URL))
            assert asset_response.status_code == 200
            assert asset_response.content.startswith(b"\x89PNG")

        archive = _request("GET", f"/api/tasks/{task_id}/download.zip")
        assert archive.status_code == 200
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zip_file:
            names = zip_file.namelist()
        assert any(name.endswith(".png") for name in names)

        history = _request("GET", "/api/history?limit=20")
        assert history.status_code == 200
        assert task_id in {task["id"] for task in history.json()["tasks"]}

        retry = _request("POST", f"/api/tasks/{task_id}/retry")
        assert retry.status_code == 400
    finally:
        _request("DELETE", f"/api/tasks/{task_id}")
