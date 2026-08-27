"""标签码生成。

从二维码改成 Code 128-C 一维码,原因是打印精度而不是编码能力:

12mm 标签可打印宽度约 9~10mm,QR 需要 29 个模块(21x21 加四周静默区)挤进去,
每个模块 0.31mm —— 203dpi 打印机一个点 0.125mm,算下来 **2.5 个点**。没法均匀
分配,有的模块占 2 点、有的占 3 点,边缘参差,解码时好时坏。

一维码只在一个方向要精度,长度可以往 30mm 铺开,条宽就能取到点距的整数倍。
Code 128 的 C 子集一个符号字符编两位数字,密度是 B 子集的两倍 —— 6 位数字
只要 68 个模块,配 0.375mm(正好 3 个点)条宽也才 25.5mm,加静默区 33mm。

**条宽比原来 QR 的模块还宽 20%,而且是整数倍。** 这是标签能不能扫出来的关键。

代价是一维码没有纠错(QR 在 ECC H 下能容 30% 破损),被划一道就废。但当前的
问题是印不准而不是印坏了,而且标签上一直印着可人工识别的资产编号兜底。
"""
import io

from barcode import Code128
from barcode.writer import SVGWriter

# 203dpi 标签机点距 0.125mm,条宽取 3 个点。300dpi(0.0847mm)的机器上
# 这个值约等于 4.4 个点,不是整数倍但余量足够大,不影响。
MODULE_WIDTH_MM = 0.375
MODULE_HEIGHT_MM = 8.0
# Code 128 规范要求两侧各留 10 倍条宽的静默区。留白不够时扫码器找不到起始符 ——
# 上一版二维码就吃过压缩静默区的亏,这里不再省。
QUIET_ZONE_RATIO = 10


def render_svg(
    barcode: str,
    module_width: float = MODULE_WIDTH_MM,
    module_height: float = MODULE_HEIGHT_MM,
) -> bytes:
    """输出按物理毫米标注的矢量条码。

    刻意不出 PNG:位图在打印时会被重采样,又回到「条宽不是点距整数倍」的老问题上。
    矢量图交给打印机自己栅格化,才能保证每根条落在整点上。
    """
    buf = io.BytesIO()
    Code128(barcode, writer=SVGWriter()).write(
        buf,
        options={
            "module_width": module_width,
            "module_height": module_height,
            "quiet_zone": module_width * QUIET_ZONE_RATIO,
            # 不要库自带的文字:标签上的可读编号是 asset_tag(PC-0001),
            # 不是这串条码数字,得由我们自己排版
            "font_size": 0,
            "text_distance": 0,
            "write_text": False,
        },
    )
    return buf.getvalue()


def estimate_width_mm(barcode: str, module_width: float = MODULE_WIDTH_MM) -> float:
    """算出这个条码印出来多宽,给前端提示用哪种标签纸。"""
    modules = len(Code128(barcode).build()[0])
    return round((modules + 2 * QUIET_ZONE_RATIO) * module_width, 1)
