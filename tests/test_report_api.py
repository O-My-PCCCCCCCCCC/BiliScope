from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config, database
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    database.set_db_path(tmp_path / "t.db")
    database.init_db()


def test_generate_and_list():
    r = client.post("/api/reports/generate", params={"type": "weekly"})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "weekly"

    items = client.get("/api/reports").json()
    assert len(items) == 1

    one = client.get(f"/api/reports/{body['id']}").json()
    assert one["stats"]["views"] == 0
