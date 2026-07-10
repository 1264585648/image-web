from __future__ import annotations

import io
import os
import uuid

import requests
from PIL import Image, ImageDraw


BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
PASSWORD = "E2e-password-123"


def _request(method: str, path_or_url: str, session: requests.Session | None = None, **kwargs) -> requests.Response:
    url = path_or_url if path_or_url.startswith(("http://", "https://")) else f"{BASE_URL}{path_or_url}"
    kwargs.setdefault("timeout", 60)
    return (session or requests).request(method, url, **kwargs)


def _register(label: str) -> requests.Session:
    session = requests.Session()
    response = _request(
        "POST",
        "/api/auth/register",
        session=session,
        json={
            "email": f"precheck-{label}-{uuid.uuid4().hex}@example.test",
            "password": PASSWORD,
            "display_name": f"Precheck {label}",
        },
    )
    assert response.status_code == 200, response.text
    session.headers.update({"Authorization": f"Bearer {response.json()['access_token']}"})
    return session


def _transparent_product() -> bytes:
    image = Image.new("RGBA", (640, 640), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((170, 110, 470, 550), radius=55, fill=(35, 95, 220, 255))
    draw.ellipse((245, 230, 395, 380), fill=(220, 235, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_source_precheck_persists_report_and_mask_with_user_isolation() -> None:
    owner = _register("owner")
    other = _register("other")

    uploaded = _request(
        "POST",
        "/api/upload",
        session=owner,
        files={"file": ("precheck-product.png", _transparent_product(), "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    source_id = uploaded.json()["id"]

    isolated = _request(
        "POST",
        "/api/compliance/analyze",
        session=other,
        json={"source_image_id": source_id, "platform": "amazon", "image_role": "main", "category": "general"},
    )
    assert isolated.status_code == 404

    analyzed = _request(
        "POST",
        "/api/compliance/analyze",
        session=owner,
        json={
            "source_image_id": source_id,
            "platform": "amazon",
            "marketplace": "US",
            "image_role": "main",
            "category": "general",
        },
    )
    assert analyzed.status_code == 200, analyzed.text
    report = analyzed.json()
    assert report["id"]
    assert report["source_image_id"] == source_id
    assert report["context"]["rule_set_version"].startswith("amazon-main")
    assert report["segmentation"]["status"] == "success"
    assert report["segmentation"]["mask_url"]
    assert report["metrics"]["mask_area_ratio"] > 0
    assert report["issues"]

    mask = _request("GET", report["segmentation"]["mask_url"])
    assert mask.status_code == 200
    assert mask.content.startswith(b"\x89PNG")

    persisted = _request("GET", f"/api/compliance/analyses/{report['id']}", session=owner)
    assert persisted.status_code == 200
    assert persisted.json()["score"] == report["score"]

    hidden = _request("GET", f"/api/compliance/analyses/{report['id']}", session=other)
    assert hidden.status_code == 404
