"""Crops the captured app frames to each slot's aspect ratio and rounds the corners (PNG with alpha),
so every picture in the deck shares one frame style."""
from pathlib import Path

from PIL import Image, ImageDraw

SRC = Path(__file__).parent / 'img'
OUT = Path(__file__).parent / 'frames'
OUT.mkdir(exist_ok=True)


def framed(name, aspect, out, focus=(0.5, 0.5), radius=26, scale_px=1400):
    im = Image.open(SRC / name).convert('RGB')
    w, h = im.size
    if w / h > aspect:  # too wide: crop width
        nw = int(h * aspect)
        x = int((w - nw) * focus[0])
        im = im.crop((x, 0, x + nw, h))
    else:
        nh = int(w / aspect)
        y = int((h - nh) * focus[1])
        im = im.crop((0, y, w, y + nh))
    if im.width > scale_px:
        im = im.resize((scale_px, int(scale_px / aspect)), Image.LANCZOS)
    r = int(radius * im.width / 1000)
    mask = Image.new('L', im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), r, fill=255)
    rgba = im.convert('RGBA')
    border = Image.new('RGBA', im.size, (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle((1, 1, im.width - 2, im.height - 2), r, outline=(255, 255, 255, 40), width=2)
    rgba = Image.alpha_composite(rgba, border)
    rgba.putalpha(Image.composite(rgba.getchannel('A'), Image.new('L', im.size, 0), mask))
    rgba.save(OUT / out)
    print(out, rgba.size)


framed('earth.jpg', 16 / 9, 'earth.png', radius=0, scale_px=1920)
framed('today.jpg', 1844 / 1080, 'today.png')
for n in ('heart', 'bones', 'mind'):
    framed(f'{n}.jpg', 3.85 / 3.3, f'{n}.png', focus=(0.5, 0.3))
framed('twin.jpg', 3.9 / 3.45, 'twin.png', focus=(0.5, 0.0))
framed('nova.jpg', 7.93 / 3.45, 'nova.png', focus=(0.5, 0.455))
framed('history.jpg', 6.0 / 3.5, 'history.png', focus=(0.5, 0.25))
framed('alerts.jpg', 2.75 / 2.05, 'alerts.png', focus=(0.5, 0.15))
framed('mc.jpg', 2.75 / 2.05, 'mc.png', focus=(0.5, 0.3))
