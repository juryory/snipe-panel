"""标签码:Code 128-C 条码。

改用一维码的理由是打印精度而不是编码能力,所以这里守的主要是「条宽能不能取到
打印点的整数倍」这条线。
"""
import re

from barcode import Code128

from app.labels import MODULE_WIDTH_MM, estimate_width_mm, render_svg
from tests.test_api import _activate, _first_category, _make_asset, _new_user

DOT_MM_203DPI = 0.125


def test_barcode_is_six_digits_and_unique(admin):
    a = _make_asset(admin, "一")
    b = _make_asset(admin, "二")
    for asset in (a, b):
        assert re.fullmatch(r"\d{6}", asset["barcode"]), asset["barcode"]
    assert a["barcode"] != b["barcode"]


def test_barcode_length_is_even(admin):
    """奇数位会逼 Code 128 从 C 子集切出去,白白多占宽度。"""
    asset = _make_asset(admin)
    assert len(asset["barcode"]) % 2 == 0


def test_barcode_actually_uses_subset_c(admin):
    """C 子集一个符号字符编两位数字 —— 这是密度优势的来源,退化了就白改了。

    6 位数字走 C:start + 3 个数据符 + 校验 + stop = 68 模块。
    同样内容若走 B 子集要 11 * 6 = 66 而不是 33,总数会明显更大。
    """
    asset = _make_asset(admin)
    modules = len(Code128(asset["barcode"]).build()[0])
    assert modules == 68, f"模块数 {modules},不像走了 C 子集"


def test_module_width_is_a_whole_number_of_printer_dots(admin):
    """这是整件事的起点:二维码那版每模块 2.5 个点,没法均匀分配才扫不出来。"""
    dots = MODULE_WIDTH_MM / DOT_MM_203DPI
    assert abs(dots - round(dots)) < 1e-9, f"条宽 {MODULE_WIDTH_MM}mm = {dots} 个点,不是整数"
    assert round(dots) == 3


def test_module_is_wider_than_the_old_qr_module(admin):
    """换码制换来的余量:比原来 9mm 里塞 29 个模块的 0.31mm 还宽。"""
    old_qr_module = 9.0 / 29
    assert MODULE_WIDTH_MM > old_qr_module


def test_printed_width_fits_a_common_label(admin):
    asset = _make_asset(admin)
    width = estimate_width_mm(asset["barcode"])
    assert width == 33.0, width  # 68 模块 + 两侧各 10 倍条宽静默区


def test_label_endpoint_returns_vector_svg_with_physical_size(admin):
    """只出矢量:位图打印时会被重采样,条宽又变回不是打印点的整数倍。"""
    asset = _make_asset(admin)
    r = admin.get(f"/api/assets/{asset['id']}/label")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")

    svg = r.content.decode("utf-8")
    width = re.search(r'width="([\d.]+)mm"', svg)
    assert width, "SVG 没有按毫米标注物理尺寸"
    assert abs(float(width.group(1)) - 33.0) < 0.1
    assert r.headers["X-Label-Width-Mm"] == "33.0"


def test_label_module_width_can_be_tuned(admin):
    """不同打印机点距不同,条宽要能调。"""
    asset = _make_asset(admin)
    narrow = admin.get(f"/api/assets/{asset['id']}/label", params={"module_width": 0.25})
    wide = admin.get(f"/api/assets/{asset['id']}/label", params={"module_width": 0.5})
    assert narrow.headers["X-Label-Width-Mm"] == "22.0"
    assert wide.headers["X-Label-Width-Mm"] == "44.0"


def test_barcode_carries_no_information_beyond_the_number(admin):
    """与二维码那版同样的约定:系统外扫到只会得到一串无意义数字。"""
    asset = _make_asset(admin)
    svg = admin.get(f"/api/assets/{asset['id']}/label").content.decode("utf-8")
    assert asset["asset_tag"] not in svg
    assert "http" not in svg.lower().replace("http://www.w3.org", "")


# ---------- 查询 ----------
def test_by_tag_accepts_both_the_barcode_and_the_asset_tag(admin):
    """扫到的是 6 位数字,手输的是 PC-0001 —— 员工不该关心这个区别。"""
    asset = _make_asset(admin)
    by_barcode = admin.get(f"/api/assets/by-tag/{asset['barcode']}")
    by_tag = admin.get(f"/api/assets/by-tag/{asset['asset_tag']}")
    assert by_barcode.status_code == by_tag.status_code == 200
    assert by_barcode.json()["id"] == by_tag.json()["id"] == asset["id"]


def test_unknown_barcode_still_returns_plain_404(admin):
    _make_asset(admin)
    r = admin.get("/api/assets/by-tag/999999")
    assert r.status_code == 404
    assert r.json()["detail"] == "未找到该设备"


# ---------- 导出 ----------
def test_csv_export_has_a_separate_barcode_column(admin):
    """精臣云打印按条码号那列生成条码,资产编号那列印成文字。"""
    a = _make_asset(admin, "一")
    r = admin.post("/api/assets/qrcodes/export?fmt=csv", json=[a["id"]])
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    header, row = text.splitlines()[0], text.splitlines()[1]
    assert header.split(",")[:2] == ["条码号", "资产编号"]
    assert row.startswith(f"{a['barcode']},{a['asset_tag']}")


def test_zip_export_contains_vector_barcodes_named_by_tag(admin):
    import io
    import zipfile

    a = _make_asset(admin, "一")
    r = admin.post("/api/assets/qrcodes/export?fmt=zip", json=[a["id"]])
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        # 文件名用资产编号,人一眼知道是哪台
        assert names == [f"{a['asset_tag']}.svg"]
        assert b"<svg" in zf.read(names[0])


# ---------- 导入的老设备 ----------
def test_imported_assets_also_get_a_barcode(admin):
    """沿用旧编号导进来的存量设备,同样要能打标签。"""
    asset = _make_asset(admin, "存量", tag="PC-8001")
    assert re.fullmatch(r"\d{6}", asset["barcode"])
    assert admin.get(f"/api/assets/{asset['id']}/label").status_code == 200


def test_regular_user_can_view_a_label(admin):
    """现场核对条码扫不扫得出来,不该只有管理员能做。"""
    asset = _make_asset(admin)
    _new_user(admin, "alice")
    alice = _activate("alice")
    assert alice.get(f"/api/assets/{asset['id']}/label").status_code == 200
