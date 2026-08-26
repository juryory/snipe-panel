"""操作日志查询,以及给 n8n 用的逾期清单。"""
from tests.test_api import _activate, _make_asset, _new_user


def test_actions_are_actually_logged(admin):
    """日志一直在写,这里确认关键动作都留下了痕迹。"""
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(f"/api/assets/{asset['id']}/checkout", json={})
    alice.post(f"/api/assets/{asset['id']}/checkin", json={})

    actions = {r["action"] for r in admin.get("/api/logs").json()["items"]}
    assert {"asset_create", "user_create", "checkout", "checkin"} <= actions


def test_logs_are_newest_first_and_paginated(admin):
    for i in range(5):
        _make_asset(admin, f"设备{i}")
    page = admin.get("/api/logs", params={"page_size": 3}).json()
    assert len(page["items"]) == 3
    assert page["total"] >= 5
    times = [r["created_at"] for r in page["items"]]
    assert times == sorted(times, reverse=True)


def test_logs_can_be_filtered_by_action_and_actor(admin):
    _make_asset(admin)
    alice_info = _new_user(admin, "alice")
    alice = _activate("alice")
    asset = _make_asset(admin, "另一台")
    alice.post(f"/api/assets/{asset['id']}/checkout", json={})

    only_creates = admin.get("/api/logs", params={"action": "asset_create"}).json()
    assert all(r["action"] == "asset_create" for r in only_creates["items"])

    by_alice = admin.get("/api/logs", params={"actor_id": alice_info["id"]}).json()
    assert by_alice["total"] >= 1
    assert all(r["actor"] == "ALICE" for r in by_alice["items"])


def test_action_has_a_readable_label(admin):
    _make_asset(admin)
    items = admin.get("/api/logs", params={"action": "asset_create"}).json()["items"]
    assert items[0]["action_label"] == "新增设备"


def test_unknown_action_falls_back_to_raw_name(admin):
    """新加的动作类型没来得及配中文时,原样显示,不能变成空白。"""
    from app.db import SessionLocal
    from app.models import ActivityLog

    db = SessionLocal()
    db.add(ActivityLog(action="brand_new_action", detail="x"))
    db.commit()
    db.close()

    items = admin.get("/api/logs", params={"action": "brand_new_action"}).json()["items"]
    assert items[0]["action_label"] == "brand_new_action"


def test_actions_list_feeds_the_filter_dropdown(admin):
    _make_asset(admin)
    actions = admin.get("/api/logs/actions").json()
    assert "asset_create" in actions
    assert actions == sorted(actions)


def test_only_admin_can_read_logs(admin):
    _new_user(admin, "alice")
    alice = _activate("alice")
    assert alice.get("/api/logs").status_code == 403
    assert alice.get("/api/logs/actions").status_code == 403


# ---------- 逾期清单 ----------
def _overdue_asset(admin, name="逾期的"):
    asset = _make_asset(admin, name)
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(
        f"/api/assets/{asset['id']}/checkout", json={"due_at": "2020-01-01T00:00:00Z"}
    )
    return asset


def test_overdue_endpoint_is_off_without_a_token(client, monkeypatch):
    """没配 token 就该整个关掉,不能默认裸奔在公网上。"""
    from app.config import settings

    monkeypatch.setattr(settings, "webhook_token", "")
    r = client.get("/api/internal/overdue")
    assert r.status_code == 404


def test_overdue_endpoint_requires_the_token(admin, client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "webhook_token", "s3cret")
    _overdue_asset(admin)

    assert client.get("/api/internal/overdue").status_code == 401
    assert client.get(
        "/api/internal/overdue", headers={"Authorization": "Bearer wrong"}
    ).status_code == 401

    r = client.get("/api/internal/overdue", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["items"][0]["borrower"] == "ALICE"
    assert data["items"][0]["days_overdue"] > 0


def test_overdue_excludes_returned_and_undue(admin, client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "webhook_token", "s3cret")
    returned = _overdue_asset(admin, "还回来了")
    admin.post(f"/api/assets/{returned['id']}/checkin", json={})

    future = _make_asset(admin, "还没到期")
    admin.post(f"/api/assets/{future['id']}/checkout", json={"due_at": "2099-01-01T00:00:00Z"})
    no_due = _make_asset(admin, "没定归还日")
    admin.post(f"/api/assets/{no_due['id']}/checkout", json={})

    r = client.get("/api/internal/overdue", headers={"Authorization": "Bearer s3cret"})
    assert r.json()["count"] == 0
