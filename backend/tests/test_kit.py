"""成套借用:相机 + 镜头 + 电池一起借。

重点是「全有或全无」—— 借走三件、第四件失败的话,人已经抱着东西走了,
台账却只记了三条,对不上。
"""
from tests.test_api import _activate, _first_category, _make_asset, _new_user


def _kit(client, assets, **kw):
    return client.post(
        "/api/checkouts/kit",
        json={"asset_ids": [a["id"] for a in assets], **kw},
    )


def test_kit_checkout_links_records_with_one_id(admin):
    a, b, c = (_make_asset(admin, f"件{i}") for i in range(3))
    _new_user(admin, "alice")
    alice = _activate("alice")

    r = _kit(alice, [a, b, c])
    assert r.status_code == 200, r.text
    records = r.json()
    assert len(records) == 3
    kit_ids = {rec["kit_id"] for rec in records}
    assert len(kit_ids) == 1 and next(iter(kit_ids))
    assert all(rec["user"]["username"] == "alice" for rec in records)


def test_kit_is_all_or_nothing(admin):
    """中间某台借不了就整批取消,不能借走一半。"""
    a = _make_asset(admin, "能借的")
    busy = _make_asset(admin, "已借出的")
    c = _make_asset(admin, "也能借的")
    _new_user(admin, "bob")
    bob = _activate("bob")
    bob.post(f"/api/assets/{busy['id']}/checkout", json={})

    _new_user(admin, "alice")
    alice = _activate("alice")
    r = _kit(alice, [a, busy, c])
    assert r.status_code == 409

    # 前面那台不能被借走
    assert admin.get(f"/api/assets/{a['id']}").json()["is_checked_out"] is False
    assert admin.get(f"/api/assets/{c['id']}").json()["is_checked_out"] is False


def test_kit_rejects_asset_under_repair(admin):
    a = _make_asset(admin, "好的")
    broken = _make_asset(admin, "坏的")
    admin.post(f"/api/assets/{broken['id']}/repairs", json={"symptom": "坏了"})
    _new_user(admin, "alice")
    alice = _activate("alice")

    assert _kit(alice, [a, broken]).status_code == 409
    assert admin.get(f"/api/assets/{a['id']}").json()["is_checked_out"] is False


def test_kit_with_unknown_asset_is_rejected(admin):
    a = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    r = alice.post("/api/checkouts/kit", json={"asset_ids": [a["id"], 9999]})
    assert r.status_code == 404
    assert admin.get(f"/api/assets/{a['id']}").json()["is_checked_out"] is False


def test_kit_can_be_returned_piece_by_piece(admin):
    """kit_id 只是把记录串起来,借的仍是一台台设备 —— 镜头先还、机身还在用是常态。"""
    a, b = _make_asset(admin, "机身"), _make_asset(admin, "镜头")
    _new_user(admin, "alice")
    alice = _activate("alice")
    _kit(alice, [a, b])

    alice.post(f"/api/assets/{b['id']}/checkin", json={})
    assert admin.get(f"/api/assets/{a['id']}").json()["is_checked_out"] is True
    assert admin.get(f"/api/assets/{b['id']}").json()["is_checked_out"] is False


def test_kit_shares_due_date(admin):
    a, b = _make_asset(admin, "一"), _make_asset(admin, "二")
    _new_user(admin, "alice")
    alice = _activate("alice")
    r = _kit(alice, [a, b], due_at="2099-01-01T10:00:00Z")
    dues = {rec["due_at"] for rec in r.json()}
    assert len(dues) == 1


def test_regular_user_cannot_kit_checkout_for_someone_else(admin):
    a = _make_asset(admin)
    other = _new_user(admin, "alice")
    _new_user(admin, "bob")
    bob = _activate("bob")
    r = _kit(bob, [a], user_id=other["id"])
    assert r.status_code == 403


def test_admin_can_kit_checkout_for_someone_else(admin):
    a, b = _make_asset(admin, "一"), _make_asset(admin, "二")
    alice = _new_user(admin, "alice")
    r = _kit(admin, [a, b], user_id=alice["id"])
    assert r.status_code == 200
    assert all(rec["user"]["username"] == "alice" for rec in r.json())


def test_empty_kit_is_rejected(admin):
    r = admin.post("/api/checkouts/kit", json={"asset_ids": []})
    assert r.status_code == 422


def test_single_checkout_has_no_kit_id(admin):
    """单台借出不该被塞进某个套件里。"""
    a = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    r = alice.post(f"/api/assets/{a['id']}/checkout", json={})
    assert r.json()["kit_id"] is None


def test_my_assets_lists_all_pieces_of_a_kit(admin):
    a, b, c = (_make_asset(admin, f"件{i}") for i in range(3))
    _new_user(admin, "alice")
    alice = _activate("alice")
    _kit(alice, [a, b, c])
    assert len(alice.get("/api/me/assets").json()) == 3
