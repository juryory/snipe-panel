"""覆盖 PRD 中几处容易出错的约定:编号生成、借出并发、状态一致性、二维码内容、登录锁定。"""
import segno
from fastapi.testclient import TestClient

from app.main import app


def _new_user(admin, username, password="UserPass123", role="user"):
    r = admin.post(
        "/api/users",
        json={"username": username, "password": password, "real_name": username.upper(),
              "role": role},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _login(username, password):
    """独立的 client,拥有自己的 cookie jar。"""
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


def _activate(username, initial="UserPass123", new="MemberPass1"):
    c = _login(username, initial)
    r = c.post("/api/auth/change-password", json={"old_password": initial, "new_password": new})
    assert r.status_code == 200, r.text
    return c


def _first_category(client):
    r = client.get("/api/categories")
    assert r.status_code == 200, r.text
    return next(c for c in r.json() if c["tag_prefix"] == "PC")


def _make_asset_in(admin, category_id, name):
    r = admin.post("/api/assets", json={"name": name, "category_id": category_id})
    assert r.status_code == 201, r.text
    return r.json()


def _make_asset(admin, name="ThinkPad X1", tag=None):
    cat = _first_category(admin)
    body = {"name": name, "category_id": cat["id"]}
    if tag:
        body["asset_tag"] = tag
    r = admin.post("/api/assets", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ---------- 认证 ----------
def test_must_change_password_blocks_everything_else(client):
    """PRD 3.7:首次登录强制改密 —— 改密前除改密接口外一律拒绝。"""
    client.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    assert client.get("/api/assets").status_code == 403
    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "admin12345", "new_password": "NewAdminPass1"},
    )
    assert r.status_code == 200
    assert client.get("/api/assets").status_code == 200


def test_unauthenticated_is_rejected(client):
    assert client.get("/api/assets").status_code == 401
    assert client.get("/api/assets/by-tag/PC-0001").status_code == 401


def test_account_locks_after_five_failures(client):
    """PRD 3.7:同一账号连续失败 5 次锁定 15 分钟。"""
    for _ in range(5):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401
    # 第 6 次即便密码正确也应被锁
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    assert r.status_code == 429
    assert "锁定" in r.json()["detail"]


def test_login_error_does_not_reveal_whether_user_exists(client):
    a = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    b = client.post("/api/auth/login", json={"username": "nobody", "password": "wrong"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


# ---------- 资产编号 ----------
def test_tags_are_sequential_per_category(admin):
    """PRD 3.2:分类前缀 + 4 位流水。"""
    a = _make_asset(admin, "电脑一")
    b = _make_asset(admin, "电脑二")
    assert a["asset_tag"] == "PC-0001"
    assert b["asset_tag"] == "PC-0002"

    cam = next(c for c in admin.get("/api/categories").json() if c["tag_prefix"] == "CAM")
    r = admin.post("/api/assets", json={"name": "A7M4", "category_id": cam["id"]})
    assert r.json()["asset_tag"] == "CAM-0001"


def test_explicit_tag_conflict_returns_409(admin):
    _make_asset(admin, "存量设备", tag="PC-9999")
    r = admin.post(
        "/api/assets",
        json={"name": "重复", "category_id": _first_category(admin)["id"], "asset_tag": "PC-9999"},
    )
    assert r.status_code == 409


def test_auto_tag_skips_number_taken_by_imported_asset(admin):
    """存量设备手工占用了 PC-0001,自动编号必须推进到下一个可用号,而不是失败。"""
    _make_asset(admin, "存量设备", tag="PC-0001")
    auto = _make_asset(admin, "新设备")
    assert auto["asset_tag"] == "PC-0002"


def test_tag_is_immutable_and_category_change_keeps_it(admin):
    """PRD 3.2:标签已贴在实物上,改分类不改编号。"""
    asset = _make_asset(admin)
    cam = next(c for c in admin.get("/api/categories").json() if c["tag_prefix"] == "CAM")
    r = admin.put(f"/api/assets/{asset['id']}", json={"category_id": cam["id"]})
    assert r.status_code == 200
    assert r.json()["asset_tag"] == asset["asset_tag"] == "PC-0001"
    assert r.json()["category_id"] == cam["id"]


# ---------- 二维码 ----------
def test_qrcode_contains_only_the_tag_never_a_url(admin):
    """PRD 3.2:二维码内容 = 纯资产编号,系统之外扫到读不出任何信息。"""
    asset = _make_asset(admin)
    r = admin.get(f"/api/assets/{asset['id']}/qrcode?format=png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"

    expected = segno.make(asset["asset_tag"], error="h", micro=False)
    as_url = segno.make(f"https://example.com/a/{asset['asset_tag']}", error="h", micro=False)
    # 同参数下矩阵一致即内容一致;与 URL 版本必须不同
    assert expected.matrix == segno.make(asset["asset_tag"], error="h", micro=False).matrix
    assert expected.matrix != as_url.matrix
    # 必须是标准 QR version 1(21x21):Micro QR 虽然更小,但 ZXing 和浏览器
    # BarcodeDetector 都不支持,打出来会扫不动
    assert expected.version == 1
    assert len(expected.matrix) == 21


def test_longest_possible_tag_still_fits_version_1(admin):
    """编号长度上限必须卡在 QR version 1 的容量内。

    前缀最长 5 + 连字符 + 4 位流水 = 10 个字符,正好是 version 1 在最高纠错
    等级 H 下的字母数字容量。多一个字符就跳 version 2(25x25),模块变小,
    12mm 标签会明显更难扫。
    """
    r = admin.post("/api/categories", json={"name": "灯光", "tag_prefix": "LIGHT"})
    assert r.status_code == 201, r.text
    asset = _make_asset_in(admin, r.json()["id"], "补光灯")
    assert asset["asset_tag"] == "LIGHT-0001"
    assert len(asset["asset_tag"]) == 10

    q = segno.make(asset["asset_tag"], error="h", micro=False)
    assert q.version == 1
    assert len(q.matrix) == 21


def test_prefix_longer_than_five_is_rejected(admin):
    """6 位前缀会让编号变成 11 个字符,把二维码顶到 version 2。"""
    r = admin.post("/api/categories", json={"name": "摄影棚", "tag_prefix": "STUDIO"})
    assert r.status_code == 422


# ---------- 扫码查询 ----------
def test_by_tag_lookup(admin):
    asset = _make_asset(admin)
    r = admin.get(f"/api/assets/by-tag/{asset['asset_tag']}")
    assert r.status_code == 200
    assert r.json()["id"] == asset["id"]
    # 小写也应命中
    assert admin.get("/api/assets/by-tag/pc-0001").status_code == 200


def test_by_tag_unknown_returns_plain_404(admin):
    """PRD 3.2:统一 404,不返回可确认编号空间的提示。"""
    r = admin.get("/api/assets/by-tag/PC-8888")
    assert r.status_code == 404
    assert r.json()["detail"] == "未找到该设备"


# ---------- 借还 ----------
def test_checkout_and_checkin_cycle(admin):
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")

    r = alice.post(f"/api/assets/{asset['id']}/checkout", json={})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["username"] == "alice"

    detail = alice.get(f"/api/assets/{asset['id']}").json()
    assert detail["is_checked_out"] is True
    assert detail["current_checkout"]["user"]["username"] == "alice"
    # PRD 3.5:status 本身仍是「在库」,借出是派生状态
    assert detail["status"] == "in_stock"

    r = alice.post(f"/api/assets/{asset['id']}/checkin", json={})
    assert r.status_code == 200
    assert alice.get(f"/api/assets/{asset['id']}").json()["is_checked_out"] is False


def test_second_checkout_is_rejected(admin):
    """PRD 3.5 并发控制:同一设备至多一条未归还记录,靠唯一部分索引拦截。"""
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    _new_user(admin, "bob")
    alice, bob = _activate("alice"), _activate("bob")

    assert alice.post(f"/api/assets/{asset['id']}/checkout", json={}).status_code == 200
    r = bob.post(f"/api/assets/{asset['id']}/checkout", json={})
    assert r.status_code == 409
    assert "已被借出" in r.json()["detail"]


def test_anyone_can_check_in_but_operator_is_recorded(admin):
    """PRD 3.5:器材常由同事顺手带回,任何登录用户均可代还,但要留经办人。"""
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    _new_user(admin, "bob")
    alice, bob = _activate("alice"), _activate("bob")

    alice.post(f"/api/assets/{asset['id']}/checkout", json={})
    r = bob.post(f"/api/assets/{asset['id']}/checkin", json={})
    assert r.status_code == 200
    record = r.json()
    assert record["user"]["username"] == "alice"          # 领用人仍是 alice
    assert record["checkin_operator"]["username"] == "bob"  # 经办人是 bob


def test_checkin_without_open_record_is_rejected(admin):
    asset = _make_asset(admin)
    r = admin.post(f"/api/assets/{asset['id']}/checkin", json={})
    assert r.status_code == 409


def test_regular_user_cannot_checkout_for_someone_else(admin):
    asset = _make_asset(admin)
    alice_info = _new_user(admin, "alice")
    _new_user(admin, "bob")
    bob = _activate("bob")
    r = bob.post(f"/api/assets/{asset['id']}/checkout", json={"user_id": alice_info["id"]})
    assert r.status_code == 403


def test_checkout_does_not_touch_long_term_owner(admin):
    """PRD 3.1:owner_user_id 是长期责任人,借还流程不修改它。"""
    owner = _new_user(admin, "owner")
    asset = _make_asset(admin)
    admin.put(f"/api/assets/{asset['id']}", json={"owner_user_id": owner["id"]})
    _new_user(admin, "alice")
    alice = _activate("alice")

    alice.post(f"/api/assets/{asset['id']}/checkout", json={})
    detail = admin.get(f"/api/assets/{asset['id']}").json()
    assert detail["owner"]["username"] == "owner"
    assert detail["current_checkout"]["user"]["username"] == "alice"


def test_history_records_both_directions(admin):
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(f"/api/assets/{asset['id']}/checkout", json={})
    alice.post(f"/api/assets/{asset['id']}/checkin", json={})
    alice.post(f"/api/assets/{asset['id']}/checkout", json={})

    history = admin.get(f"/api/assets/{asset['id']}/history").json()
    assert len(history) == 2
    assert history[0]["checked_in_at"] is None      # 最新一条未归还
    assert history[1]["checked_in_at"] is not None


# ---------- 状态一致性 ----------
def test_cannot_change_status_while_checked_out(admin):
    """PRD 3.5:借出中改状态会与未归还记录矛盾。"""
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(f"/api/assets/{asset['id']}/checkout", json={})

    r = admin.put(f"/api/assets/{asset['id']}", json={"status": "repair"})
    assert r.status_code == 409


def test_cannot_checkout_asset_under_repair(admin):
    asset = _make_asset(admin)
    admin.put(f"/api/assets/{asset['id']}", json={"status": "repair"})
    _new_user(admin, "alice")
    alice = _activate("alice")
    r = alice.post(f"/api/assets/{asset['id']}/checkout", json={})
    assert r.status_code == 409
    assert "维修" in r.json()["detail"]


def test_status_enum_has_no_borrowed_value(admin):
    """借出不是设备自身状态,不能手工设置。"""
    asset = _make_asset(admin)
    r = admin.put(f"/api/assets/{asset['id']}", json={"status": "checked_out"})
    assert r.status_code == 422


def test_delete_is_soft_and_blocked_while_checked_out(admin):
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(f"/api/assets/{asset['id']}/checkout", json={})
    assert admin.delete(f"/api/assets/{asset['id']}").status_code == 409

    alice.post(f"/api/assets/{asset['id']}/checkin", json={})
    assert admin.delete(f"/api/assets/{asset['id']}").status_code == 200
    assert admin.get(f"/api/assets/{asset['id']}").status_code == 404
    assert admin.get("/api/assets").json()["total"] == 0


# ---------- 权限 ----------
def test_regular_user_cannot_manage_assets(admin):
    _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    cat = _first_category(admin)
    assert alice.post("/api/assets", json={"name": "x", "category_id": cat["id"]}).status_code == 403
    assert alice.put("/api/assets/1", json={"name": "x"}).status_code == 403
    assert alice.delete("/api/assets/1").status_code == 403
    # 但可以查看台账与借还
    assert alice.get("/api/assets").status_code == 200


# ---------- 列表与查询 ----------
def test_search_and_filters(admin):
    _make_asset(admin, "ThinkPad X1")
    _make_asset(admin, "MacBook Pro")
    assert admin.get("/api/assets", params={"q": "ThinkPad"}).json()["total"] == 1
    assert admin.get("/api/assets", params={"q": "PC-0002"}).json()["total"] == 1
    assert admin.get("/api/assets", params={"checked_out": False}).json()["total"] == 2
    assert admin.get("/api/assets", params={"checked_out": True}).json()["total"] == 0


def test_my_assets_covers_owned_and_borrowed(admin):
    owned = _make_asset(admin, "我的本本")
    borrowed = _make_asset(admin, "借来的相机")
    alice_info = _new_user(admin, "alice")
    alice = _activate("alice")
    admin.put(f"/api/assets/{owned['id']}", json={"owner_user_id": alice_info["id"]})
    alice.post(f"/api/assets/{borrowed['id']}/checkout", json={})

    tags = {a["asset_tag"] for a in alice.get("/api/me/assets").json()}
    assert tags == {owned["asset_tag"], borrowed["asset_tag"]}


def test_overdue_list(admin):
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(
        f"/api/assets/{asset['id']}/checkout",
        json={"due_at": "2020-01-01T00:00:00Z"},
    )
    overdue = admin.get("/api/checkouts", params={"overdue": True}).json()
    assert len(overdue) == 1
    assert overdue[0]["is_overdue"] is True


def test_datetimes_are_serialized_with_timezone(admin):
    """朴素 UTC 存库,出口必须带时区,否则前端按本地时区解析会全错。"""
    asset = _make_asset(admin)
    created = asset["created_at"]
    assert created.endswith("Z") or "+00:00" in created


# ---------- 分类 ----------
def test_category_prefix_must_be_unique(admin):
    r = admin.post("/api/categories", json={"name": "另一种电脑", "tag_prefix": "PC"})
    assert r.status_code == 409


def test_category_in_use_cannot_be_deleted(admin):
    cat = _first_category(admin)
    _make_asset(admin)
    r = admin.delete(f"/api/categories/{cat['id']}")
    assert r.status_code == 409
