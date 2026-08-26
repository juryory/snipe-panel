"""生成 PWA 图标。

不依赖 Pillow —— 只画矩形,直接手写 PNG 就够了,免得为了几个图标往项目里塞
一个几十兆的图像库。图案是三个二维码定位图形,一眼能看出是扫码类应用。

图案控制在画布中心 60% 见方,满足 maskable 的安全区要求(中心 80%),
所以 Android 把图标裁成圆形也不会切到内容。

改完跑:python scripts/make_icons.py
"""
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "public"

BG = (31, 41, 55)        # #1f2937,与 manifest 的 theme_color 一致
FG = (255, 255, 255)

# 图案在 100x100 逻辑网格上定义,再等比放大到实际尺寸
FINDERS = [(0, 0), (70, 0), (0, 70)]   # 左上、右上、左下,和真实二维码一致
FINDER_SIZE = 30
# 右下角撒几个数据点,让它更像二维码而不是三个方框
DOTS = [(62, 62), (78, 62), (94, 62), (62, 78), (86, 78), (70, 94), (94, 94)]
DOT_SIZE = 8


def _rect(px, size, x0, y0, w, h, color):
    """在 size x size 的像素缓冲上填一个矩形,坐标是 100 网格单位。"""
    scale = size / 100.0
    left, top = int(x0 * scale), int(y0 * scale)
    right, bottom = int((x0 + w) * scale), int((y0 + h) * scale)
    for y in range(max(0, top), min(size, bottom)):
        row = px[y]
        for x in range(max(0, left), min(size, right)):
            row[x] = color


def render(size: int) -> bytes:
    px = [[BG] * size for _ in range(size)]

    # 图案整体缩到中心 60%(20..80),留出 maskable 安全边
    def place(x, y, w, h, color):
        _rect(px, size, 20 + x * 0.6, 20 + y * 0.6, w * 0.6, h * 0.6, color)

    for ox, oy in FINDERS:
        s = FINDER_SIZE
        ring = s / 7.0  # 定位图形是 7 模块宽,外环占 1 模块
        place(ox, oy, s, s, FG)
        place(ox + ring, oy + ring, s - 2 * ring, s - 2 * ring, BG)
        place(ox + 2 * ring, oy + 2 * ring, s - 4 * ring, s - 4 * ring, FG)

    for dx, dy in DOTS:
        place(dx, dy, DOT_SIZE, DOT_SIZE, FG)

    return _encode_png(px, size)


def _encode_png(px, size: int) -> bytes:
    raw = bytearray()
    for row in px:
        raw.append(0)  # 每行的 filter 类型:0 = None
        for r, g, b in row:
            raw += bytes((r, g, b))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8 位真彩色
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in [
        ("icon-192.png", 192),
        ("icon-512.png", 512),
        ("apple-touch-icon.png", 180),  # iOS 不读 manifest 的图标,只认这个
    ]:
        path = OUT / name
        path.write_bytes(render(size))
        print(f"{path.name}  {size}x{size}  {path.stat().st_size} 字节")
