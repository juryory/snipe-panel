"""盘库(滚动盘点)。

覆盖:空 body 即确认无误、最后盘库派生、管理员当场写回 vs 普通用户挂起、
差异处理、借出中设备的状态差异、超期未盘清单、台账快照。
"""
from tests.test_api import _activate, _first_category, _make_asset, _new_user


def _set_location(admin, asset, location):
    r = admin.put(f"/api/assets/{asset['id']}", json={"location": location})
    assert r.status_code == 200, r.text
    return r.json()


def test_check_with_empty_body_means_confirmed_as_is(admin):
    """连续扫码盘库:body 为空 = 与台账一致,一次调用完成一台。"""
    asset = _make_asset(admin)
    _set_location(admin, asset, "库房 A")

    r = admin.post(f"/api/assets/{asset['id']}/check", json={})
    assert r.status_code == 200, r.text
    check = r.json()
    assert check["has_discrepancy"] is False
    assert check["observed_location"] == "库房 A"
    assert check["checked_by"]["username"] == "admin"


def test_last_check_surfaces_on_the_asset(admin):
    """最后盘库时间派生自盘库记录,不在设备表上冗余字段。"""
    asset = _make_asset(admin)
    assert admin.get(f"/api/assets/{asset['id']}").json()["last_check"] is None

    admin.post(f"/api/assets/{asset['id']}/check", json={})
    last = admin.get(f"/api/assets/{asset['id']}").json()["last_check"]
    assert last["checked_by"]["username"] == "admin"
    assert last["has_discrepancy"] is False
    # 列表页也要带上,否则台账看不出哪些该盘了
    assert admin.get("/api/assets").json()["items"][0]["last_check"] is not None


def test_admin_check_applies_the_correction_immediately(admin):
    asset = _make_asset(admin)
    _set_location(admin, asset, "库房 A")

    check = admin.post(
        f"/api/assets/{asset['id']}/check", json={"observed_location": "演播室 B"}
    ).json()
    assert check["has_discrepancy"] is True
    assert check["applied"] is True
    assert check["pending"] is False
    # 台账当场就被改了
    assert admin.get(f"/api/assets/{asset['id']}").json()["location"] == "演播室 B"


def test_regular_user_check_is_recorded_but_not_applied(admin):
    """普通用户盘出的差异只记录,挂起等管理员确认,台账不动。"""
    asset = _make_asset(admin)
    _set_location(admin, asset, "库房 A")
    _new_user(admin, "alice")
    alice = _activate("alice")

    r = alice.post(f"/api/assets/{asset['id']}/check", json={"observed_location": "演播室 B"})
    assert r.status_code == 200, r.text
    check = r.json()
    assert check["has_discrepancy"] is True
    assert check["applied"] is False
    assert check["pending"] is True
    assert admin.get(f"/api/assets/{asset['id']}").json()["location"] == "库房 A"


def test_pending_discrepancy_shows_up_and_can_be_applied(admin):
    asset = _make_asset(admin)
    _set_location(admin, asset, "库房 A")
    _new_user(admin, "alice")
    alice = _activate("alice")
    check = alice.post(
        f"/api/assets/{asset['id']}/check", json={"observed_location": "演播室 B"}
    ).json()

    pending = admin.get("/api/inventory/checks", params={"pending": True}).json()
    assert len(pending) == 1
    assert pending[0]["id"] == check["id"]

    r = admin.post(f"/api/inventory/checks/{check['id']}/resolve", json={"action": "apply"})
    assert r.status_code == 200
    assert r.json()["applied"] is True
    assert admin.get(f"/api/assets/{asset['id']}").json()["location"] == "演播室 B"
    assert admin.get("/api/inventory/checks", params={"pending": True}).json() == []


def test_discrepancy_can_be_dismissed_keeping_the_ledger(admin):
    asset = _make_asset(admin)
    _set_location(admin, asset, "库房 A")
    _new_user(admin, "alice")
    alice = _activate("alice")
    check = alice.post(
        f"/api/assets/{asset['id']}/check", json={"observed_location": "看错了"}
    ).json()

    r = admin.post(f"/api/inventory/checks/{check['id']}/resolve", json={"action": "dismiss"})
    assert r.status_code == 200
    assert r.json()["applied"] is False
    assert r.json()["pending"] is False
    # 台账维持原值,记录留档
    assert admin.get(f"/api/assets/{asset['id']}").json()["location"] == "库房 A"


def test_same_discrepancy_cannot_be_resolved_twice(admin):
    asset = _make_asset(admin)
    _set_location(admin, asset, "库房 A")
    _new_user(admin, "alice")
    alice = _activate("alice")
    check = alice.post(
        f"/api/assets/{asset['id']}/check", json={"observed_location": "演播室 B"}
    ).json()

    assert admin.post(
        f"/api/inventory/checks/{check['id']}/resolve", json={"action": "apply"}
    ).status_code == 200
    r = admin.post(f"/api/inventory/checks/{check['id']}/resolve", json={"action": "apply"})
    assert r.status_code == 409


def test_checking_a_borrowed_asset_records_the_borrower(admin):
    """在同事桌上盘到设备是正常情况,不算异常,但要记下当时借给谁。"""
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(f"/api/assets/{asset['id']}/checkout", json={})

    check = admin.post(f"/api/assets/{asset['id']}/check", json={}).json()
    assert check["borrower"]["username"] == "alice"
    assert check["has_discrepancy"] is False


def test_status_change_on_borrowed_asset_stays_pending(admin):
    """借出中不允许改状态(PRD 3.5),所以即便管理员盘出状态差异也只挂起。"""
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(f"/api/assets/{asset['id']}/checkout", json={})

    check = admin.post(
        f"/api/assets/{asset['id']}/check", json={"observed_status": "repair"}
    ).json()
    assert check["has_discrepancy"] is True
    assert check["applied"] is False
    assert check["pending"] is True
    assert admin.get(f"/api/assets/{asset['id']}").json()["status"] == "in_stock"

    # 归还前采纳应被拒绝
    r = admin.post(f"/api/inventory/checks/{check['id']}/resolve", json={"action": "apply"})
    assert r.status_code == 409
    assert "归还" in r.json()["detail"]

    # 归还后就能采纳了
    alice.post(f"/api/assets/{asset['id']}/checkin", json={})
    r = admin.post(f"/api/inventory/checks/{check['id']}/resolve", json={"action": "apply"})
    assert r.status_code == 200
    assert admin.get(f"/api/assets/{asset['id']}").json()["status"] == "repair"


def test_unchecked_days_filter_is_the_todo_list(admin):
    """滚动盘点的核心:超期未盘列表 = 还没盘到的设备(含从未盘过的)。"""
    a = _make_asset(admin, "盘过的")
    b = _make_asset(admin, "没盘过的")
    admin.post(f"/api/assets/{a['id']}/check", json={})

    todo = admin.get("/api/assets", params={"unchecked_days": 90}).json()
    assert todo["total"] == 1
    assert todo["items"][0]["id"] == b["id"]

    # 边界:0 天口径 = 「盘库时间超过 0 天的都算」,刚盘过的也在列表里,即全部
    assert admin.get("/api/assets", params={"unchecked_days": 0}).json()["total"] == 2


def test_summary_counts(admin):
    a = _make_asset(admin, "一")
    _make_asset(admin, "二")
    admin.post(f"/api/assets/{a['id']}/check", json={})
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(f"/api/assets/{a['id']}/check", json={"observed_location": "别处"})

    s = admin.get("/api/inventory/summary", params={"unchecked_days": 90}).json()
    assert s["total"] == 2
    assert s["checked"] == 1
    assert s["overdue"] == 1
    assert s["pending_discrepancies"] == 1


def test_check_history_is_newest_first(admin):
    asset = _make_asset(admin)
    admin.post(f"/api/assets/{asset['id']}/check", json={"note": "第一次"})
    admin.post(f"/api/assets/{asset['id']}/check", json={"note": "第二次"})
    rows = admin.get(f"/api/assets/{asset['id']}/checks").json()
    assert [r["note"] for r in rows] == ["第二次", "第一次"]


def test_regular_user_sees_only_own_checks_and_cannot_resolve(admin):
    asset = _make_asset(admin)
    _set_location(admin, asset, "库房 A")
    _new_user(admin, "alice")
    alice = _activate("alice")
    admin.post(f"/api/assets/{asset['id']}/check", json={})
    check = alice.post(
        f"/api/assets/{asset['id']}/check", json={"observed_location": "演播室 B"}
    ).json()

    mine = alice.get("/api/inventory/checks").json()
    assert len(mine) == 1
    assert mine[0]["checked_by"]["username"] == "alice"
    assert len(admin.get("/api/inventory/checks").json()) == 2

    r = alice.post(f"/api/inventory/checks/{check['id']}/resolve", json={"action": "apply"})
    assert r.status_code == 403


def test_check_snapshots_the_ledger_value_at_that_moment(admin):
    """快照必须存下来:台账后来又被改过的话,光比对当前值就对不上了。"""
    asset = _make_asset(admin)
    _set_location(admin, asset, "库房 A")
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(f"/api/assets/{asset['id']}/check", json={"observed_location": "演播室 B"})

    # 管理员事后又把位置改到第三个值
    _set_location(admin, asset, "库房 C")

    check = admin.get("/api/inventory/checks", params={"pending": True}).json()[0]
    assert check["location_at_check"] == "库房 A"    # 盘库当时台账里是这个
    assert check["observed_location"] == "演播室 B"  # 现场看到的是这个


def test_note_records_usage_condition(admin):
    """使用情况备注:盘库时对设备状况的文字记录。"""
    asset = _make_asset(admin)
    check = admin.post(
        f"/api/assets/{asset['id']}/check", json={"note": "外壳有磕碰,功能正常"}
    ).json()
    assert check["note"] == "外壳有磕碰,功能正常"
    assert check["has_discrepancy"] is False
