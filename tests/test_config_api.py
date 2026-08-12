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


def test_get_config_defaults():
    body = client.get("/api/config").json()
    assert "smtp" in body
    assert "task_interval" in body


def test_post_config_saves_and_masks_password():
    client.post("/api/config", json={"smtp": {
        "host": "smtp.qq.com", "port": 465, "user": "a@qq.com",
        "password": "mysecret", "to": "b@qq.com",
    }})
    cfg = config.load_config()
    assert cfg["smtp"]["password"] == "mysecret"

    body = client.get("/api/config").json()
    assert body["smtp"]["password"] == "******"


def test_post_config_keeps_password_when_masked():
    config.save_config({"smtp": {"host": "smtp.qq.com", "port": 465, "user": "a@qq.com",
                                  "password": "realpw", "to": "b@qq.com"}})
    client.post("/api/config", json={"smtp": {"host": "smtp.qq.com", "password": "******"}})
    assert config.load_config()["smtp"]["password"] == "realpw"
