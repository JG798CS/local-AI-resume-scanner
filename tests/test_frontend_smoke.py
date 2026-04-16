from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app as app_module
from store import store


def test_frontend_assets_exist() -> None:
    root = Path(__file__).resolve().parents[1] / 'frontend'
    assert (root / 'index.html').exists()
    assert (root / 'app.js').exists()
    assert (root / 'styles.css').exists()


def test_ui_route_serves_frontend() -> None:
    store.reset()
    client = TestClient(app_module.app)
    response = client.get('/ui')
    assert response.status_code == 200
    assert 'Hiring Workflow' in response.text
    assert '/ui/app.js' in response.text
