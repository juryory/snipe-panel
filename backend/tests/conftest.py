import os
import tempfile
from pathlib import Path

import pytest

# 必须在导入 app 之前设置,config 在导入时就确定了库路径
_TMP = Path(tempfile.mkdtemp(prefix="snipe-test-"))
os.environ["SNIPE_DB_PATH"] = str(_TMP / "test.db")
os.environ["SNIPE_SECRET_KEY"] = "test-secret"
os.environ["SNIPE_INITIAL_ADMIN_PASSWORD"] = "admin12345"
# 每个用例都重建库,跑迁移纯属浪费;迁移本身由 test_migrations.py 单独验证
os.environ["SNIPE_RUN_MIGRATIONS"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app, bootstrap  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    ratelimit._WINDOWS.clear()  # 限流是进程内状态,不清会跨用例累积
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    """登录初始管理员并完成首次改密(PRD 3.7 强制)。"""
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    assert r.status_code == 200, r.text
    assert r.json()["must_change_password"] is True
    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "admin12345", "new_password": "NewAdminPass1"},
    )
    assert r.status_code == 200, r.text
    return client
