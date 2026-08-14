# -*- coding: utf-8 -*-
"""生成 BiliScope 图标：粉色圆角方块 + 白色上升数据柱。"""
from PIL import Image, ImageDraw

TOP = (251, 114, 153)     # #fb7299 亮粉
BOTTOM = (224, 66, 114)   # 深一点的粉


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 垂直渐变背景
    for y in range(size):
        t = y / size
        color = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)) + (255,)
        d.line([(0, y), (size, y)], fill=color)
    # 圆角遮罩
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)
    img.putalpha(mask)
    d = ImageDraw.Draw(img)
    # 白色上升数据柱（4 根）
    bar_w = int(size * 0.11)
    gap = int(size * 0.065)
    x0 = int(size * 0.17)
    base_y = int(size * 0.86)
    heights = [0.30, 0.45, 0.60, 0.76]
    for i, h in enumerate(heights):
        x = x0 + i * (bar_w + gap)
        top_y = base_y - int(h * size * 0.82)
        d.rounded_rectangle([x, top_y, x + bar_w, base_y], radius=int(bar_w * 0.4), fill=(255, 255, 255, 255))
    return img


if __name__ == "__main__":
    img = draw_icon(256)
    img.save("app_icon.ico", sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)])
    draw_icon(64).save("web/favicon.png")
    print("icons generated")
