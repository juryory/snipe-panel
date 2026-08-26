"""报修记录。

重点在状态联动:报修/结案要怎么带动设备状态,以及和「借出中不允许改状态」
这条既有规则怎么共存。
"""
from tests.test_api import _activate, _first_category, _make_asset, _new_user


def _report(client, asset, symptom="快门失灵", **kw):
    r = client.post(f"/api/assets/{asset['id']}/repairs", json={"symptom": symptom, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _asset(client, asset):
    return client.get(f"/api/assets/{asset['id']}").json()


# ---------- 基本流转 ----------
def test_reporting_a_repair_puts_the_asset_into_repair(admin):
    asset = _make_asset(admin)
    record = _report(admin, asset, "开不了机")
    assert record["is_open"] is True
    assert record["symptom"] == "开不了机"
    assert _asset(admin, asset)["status"] == "repair"
    # 在修中是派生的,列表页要能看出来
    assert _asset(admin, asset)["open_repair_id"] == record["id"]


def test_closing_as_fixed_returns_the_asset_to_stock(admin):
    asset = _make_asset(admin)
    record = _report(admin, asset)
    r = admin.post(f"/api/repairs/{record['id']}/close",
                   json={"result": "fixed", "cost_yuan": 380.5})
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["is_open"] is False
    assert done["result_label"] == "已修好"
    assert done["cost_yuan"] == 380.5
    assert _asset(admin, asset)["status"] == "in_stock"
    assert _asset(admin, asset)["open_repair_id"] is None


def test_closing_as_scrapped_retires_the_asset(admin):
    asset = _make_asset(admin)
    record = _report(admin, asset)
    admin.post(f"/api/repairs/{record['id']}/close", json={"result": "scrapped"})
    assert _asset(admin, asset)["status"] == "retired"


def test_closing_as_cancelled_returns_to_stock(admin):
    """误报:设备其实没坏,状态该回在库而不是留在维修。"""
    asset = _make_asset(admin)
    record = _report(admin, asset)
    admin.post(f"/api/repairs/{record['id']}/close", json={"result": "cancelled"})
    assert _asset(admin, asset)["status"] == "in_stock"


def test_cost_is_stored_in_cents(admin):
    """用浮点存钱迟早出现 0.1+0.2 这种账,库里存分,出口换算成元。"""
    asset = _make_asset(admin)
    record = _report(admin, asset)
    r = admin.post(f"/api/repairs/{record['id']}/close",
                   json={"result": "fixed", "cost_yuan": 0.1 + 0.2})
    assert r.json()["cost_yuan"] == 0.3


# ---------- 并发与重复 ----------
def test_only_one_open_repair_per_asset(admin):
    asset = _make_asset(admin)
    _report(admin, asset)
    r = admin.post(f"/api/assets/{asset['id']}/repairs", json={"symptom": "又坏了"})
    assert r.status_code == 409
    assert "未完结" in r.json()["detail"]


def test_can_report_again_after_closing(admin):
    asset = _make_asset(admin)
    first = _report(admin, asset, "第一次坏")
    admin.post(f"/api/repairs/{first['id']}/close", json={"result": "fixed"})
    second = _report(admin, asset, "第二次坏")
    assert second["id"] != first["id"]
    assert len(admin.get(f"/api/assets/{asset['id']}/repairs").json()) == 2


def test_closed_repair_cannot_be_closed_or_edited_again(admin):
    asset = _make_asset(admin)
    record = _report(admin, asset)
    admin.post(f"/api/repairs/{record['id']}/close", json={"result": "fixed"})
    assert admin.post(f"/api/repairs/{record['id']}/close",
                      json={"result": "fixed"}).status_code == 409
    assert admin.put(f"/api/repairs/{record['id']}", json={"note": "补充"}).status_code == 409


def test_retired_asset_cannot_be_reported(admin):
    asset = _make_asset(admin)
    admin.put(f"/api/assets/{asset['id']}", json={"status": "retired"})
    r = admin.post(f"/api/assets/{asset['id']}/repairs", json={"symptom": "x"})
    assert r.status_code == 409
    assert "报废" in r.json()["detail"]


# ---------- 与借还的交界 ----------
def test_reporting_a_borrowed_asset_defers_the_status_change(admin):
    """设备在别人手上坏掉:记录照样建,但状态先不动 —— 借出中不允许改状态。"""
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(f"/api/assets/{asset['id']}/checkout", json={})

    record = alice.post(f"/api/assets/{asset['id']}/repairs",
                        json={"symptom": "摔了一下"})
    assert record.status_code == 200, record.text
    assert _asset(admin, asset)["status"] == "in_stock"  # 还没翻

    # 归还这一刻才是把它翻成维修的正确时机
    alice.post(f"/api/assets/{asset['id']}/checkin", json={})
    assert _asset(admin, asset)["status"] == "repair"


def test_asset_with_open_repair_cannot_be_checked_out(admin):
    asset = _make_asset(admin)
    _report(admin, asset)
    _new_user(admin, "alice")
    alice = _activate("alice")
    r = alice.post(f"/api/assets/{asset['id']}/checkout", json={})
    assert r.status_code == 409


def test_scrapping_while_borrowed_still_retires(admin):
    """判定报废是终态,不受借出中不改状态的限制 —— 东西已经没了。"""
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    alice.post(f"/api/assets/{asset['id']}/checkout", json={})
    record = alice.post(f"/api/assets/{asset['id']}/repairs", json={"symptom": "泡水"}).json()

    admin.post(f"/api/repairs/{record['id']}/close", json={"result": "scrapped"})
    assert _asset(admin, asset)["status"] == "retired"


# ---------- 保修 ----------
def test_warranty_flag_is_captured_at_report_time(admin):
    cat = _first_category(admin)
    in_warranty = admin.post("/api/assets", json={
        "name": "还在保", "category_id": cat["id"], "warranty_until": "2099-01-01",
    }).json()
    expired = admin.post("/api/assets", json={
        "name": "过保了", "category_id": cat["id"], "warranty_until": "2020-01-01",
    }).json()

    assert admin.get(f"/api/assets/{in_warranty['id']}").json()["warranty_valid"] is True
    assert admin.get(f"/api/assets/{expired['id']}").json()["warranty_valid"] is False

    assert _report(admin, in_warranty)["under_warranty"] is True
    assert _report(admin, expired)["under_warranty"] is False


def test_no_warranty_date_means_unknown_not_false(admin):
    asset = _make_asset(admin)
    assert _asset(admin, asset)["warranty_valid"] is None


# ---------- 厂商与进度 ----------
def test_vendor_and_progress_can_be_filled_in_later(admin):
    vendor = admin.post("/api/companies", json={"name": "维修站"}).json()
    asset = _make_asset(admin)
    record = _report(admin, asset)

    r = admin.put(f"/api/repairs/{record['id']}", json={
        "vendor_id": vendor["id"], "cost_yuan": 200, "note": "已寄出",
    })
    assert r.status_code == 200, r.text
    assert r.json()["vendor"]["name"] == "维修站"
    assert r.json()["cost_yuan"] == 200.0


def test_unknown_vendor_is_rejected(admin):
    asset = _make_asset(admin)
    r = admin.post(f"/api/assets/{asset['id']}/repairs",
                   json={"symptom": "x", "vendor_id": 999})
    assert r.status_code == 400


# ---------- 列表与权限 ----------
def test_open_repairs_list_is_the_worklist(admin):
    a = _make_asset(admin, "坏的")
    b = _make_asset(admin, "也坏的")
    _report(admin, a)
    second = _report(admin, b)
    admin.post(f"/api/repairs/{second['id']}/close", json={"result": "fixed"})

    open_only = admin.get("/api/repairs").json()
    assert [r["asset_name"] for r in open_only] == ["坏的"]
    assert len(admin.get("/api/repairs", params={"open_only": False}).json()) == 2


def test_anyone_can_report_but_only_admin_closes(admin):
    """发现设备坏的往往是借用人,不是管理员。"""
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")

    record = alice.post(f"/api/assets/{asset['id']}/repairs",
                        json={"symptom": "屏幕有条纹"})
    assert record.status_code == 200
    assert record.json()["reported_by"]["username"] == "alice"

    rid = record.json()["id"]
    assert alice.post(f"/api/repairs/{rid}/close", json={"result": "fixed"}).status_code == 403
    assert alice.put(f"/api/repairs/{rid}", json={"note": "x"}).status_code == 403


def test_days_open_counts_from_report(admin):
    asset = _make_asset(admin)
    record = _report(admin, asset)
    assert record["days_open"] == 0
