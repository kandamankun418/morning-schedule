"""PWA用のアイコン(docs/icon.png)を外部ライブラリなしで生成する。一度実行すれば十分。"""
from __future__ import annotations

import math
import os
import struct
import zlib

SIZE = 512
BG = (31, 111, 235)
FG = (255, 255, 255)


def _rounded(x: int, y: int, size: int, radius: int) -> bool:
    for cx, cy in ((radius, radius), (size - radius, radius),
                   (radius, size - radius), (size - radius, size - radius)):
        if (x < radius or x > size - radius) and (y < radius or y > size - radius):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                return True
            continue
    return not ((x < radius or x > size - radius) and (y < radius or y > size - radius))


def _on_hand(x: float, y: float, cx: float, cy: float,
             clock_hour: float, length: float, half_width: float) -> bool:
    """中心から時計の clock_hour 方向へ伸びる針の上に乗っているか。"""
    angle = math.radians(clock_hour / 12.0 * 360.0)  # 12時=0、時計回り
    dx, dy = x - cx, y - cy
    along = dx * math.sin(angle) - dy * math.cos(angle)   # 針の向きの成分
    across = dx * math.cos(angle) + dy * math.sin(angle)  # 針と直交する成分
    return 0 <= along <= length and abs(across) <= half_width


def build_rows() -> bytes:
    cx = cy = SIZE / 2.0
    outer, inner = SIZE * 0.30, SIZE * 0.255
    rows = bytearray()
    for y in range(SIZE):
        rows.append(0)  # フィルタタイプ: なし
        for x in range(SIZE):
            if not _rounded(x, y, SIZE, int(SIZE * 0.22)):
                rows.extend((0, 0, 0))
                continue
            color = BG
            d = math.hypot(x - cx, y - cy)
            if inner <= d <= outer:
                color = FG  # 時計の文字盤
            elif d < inner:
                # 5:00 を指す針（長針=12の方向、短針=5の方向）
                if _on_hand(x, y, cx, cy, 0, inner * 0.88, SIZE * 0.016):
                    color = FG
                elif _on_hand(x, y, cx, cy, 5, inner * 0.60, SIZE * 0.020):
                    color = FG
            rows.extend(color)
    return bytes(rows)


def chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def main() -> None:
    docs = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    os.makedirs(docs, exist_ok=True)
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(build_rows(), 9))
        + chunk(b"IEND", b"")
    )
    path = os.path.join(docs, "icon.png")
    with open(path, "wb") as f:
        f.write(png)
    print("wrote {} ({} bytes)".format(path, len(png)))


if __name__ == "__main__":
    main()
