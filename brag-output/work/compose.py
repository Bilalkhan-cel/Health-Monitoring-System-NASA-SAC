"""Joins the captured scenes with dips through black on each cut, bakes the poster in as frame 0,
and muxes the score. Usage: compose.py <out.mp4> [--poster path.jpg] [--preview N]"""
import argparse
import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image

HERE = Path(__file__).parent
FPS = 30
SCENES = ['hero', 'today', 'doctor', 'mc', 'outro']
OUT_FRAMES = 5   # outgoing: push and fade to black
IN_FRAMES = 7    # incoming: settle in from black


def ease_out(x):
    return 1 - (1 - x) ** 3


def zoom(img, scale):
    if abs(scale - 1) < 1e-4:
        return img
    w, h = img.size
    big = img.resize((round(w * scale), round(h * scale)), Image.BICUBIC)
    l, t = (big.width - w) // 2, (big.height - h) // 2
    return big.crop((l, t, l + w, t + h))


def frames():
    for si, name in enumerate(SCENES):
        files = sorted((HERE / 'frames' / name).glob('*.jpg'))
        n = len(files)
        for i, f in enumerate(files):
            img = Image.open(f).convert('RGB')
            bright = 1.0
            scale = 1.0
            if si > 0 and i < IN_FRAMES:
                p = ease_out((i + 1) / (IN_FRAMES + 1))
                bright *= p
                scale *= 1.035 - 0.035 * p
            if si < len(SCENES) - 1 and i >= n - OUT_FRAMES:
                p = (i - (n - OUT_FRAMES) + 1) / (OUT_FRAMES + 1)
                bright *= 1 - p ** 1.6
                scale *= 1 + 0.03 * p ** 2
            if si == len(SCENES) - 1 and i >= n - 15:
                bright *= 1 - ((i - (n - 15) + 1) / 15) ** 1.4
            img = zoom(img, scale)
            if bright < 0.999:
                img = Image.fromarray((np.asarray(img, dtype=np.float32) * bright).astype(np.uint8))
            yield img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--poster')
    ap.add_argument('--audio', default=str(HERE / 'audio' / 'score.wav'))
    args = ap.parse_args()

    out = av.open(args.out, 'w')
    vs = out.add_stream('libx264', rate=FPS)
    vs.width, vs.height, vs.pix_fmt = 1920, 1080, 'yuv420p'
    vs.options = {'crf': '17', 'preset': 'slow', 'profile': 'high', 'movflags': '+faststart'}
    vs.codec_context.time_base = Fraction(1, FPS)

    with wave.open(args.audio) as w:
        sr = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), '<i2').reshape(-1, 2)
    as_ = out.add_stream('aac', rate=sr)
    as_.layout = 'stereo'
    as_.bit_rate = 192000

    count = 0
    for k, img in enumerate(frames()):
        if k == 0 and args.poster:
            img = Image.open(args.poster).convert('RGB')
        vf = av.VideoFrame.from_image(img)
        vf.pts = k
        vf.time_base = Fraction(1, FPS)
        for p in vs.encode(vf):
            out.mux(p)
        count += 1
    for p in vs.encode():
        out.mux(p)

    # Trim/pad audio to the exact video length.
    need = round(count / FPS * sr)
    pcm = pcm[:need] if len(pcm) >= need else np.vstack([pcm, np.zeros((need - len(pcm), 2), '<i2')])
    step = 1024
    for i in range(0, need, step):
        chunk = np.ascontiguousarray(pcm[i:i + step].T.astype(np.float32) / 32768)
        af = av.AudioFrame.from_ndarray(chunk, format='fltp', layout='stereo')
        af.sample_rate = sr
        af.pts = i
        af.time_base = Fraction(1, sr)
        for p in as_.encode(af):
            out.mux(p)
    for p in as_.encode():
        out.mux(p)
    out.close()
    print(f'{args.out}: {count} frames, {count / FPS:.2f}s')


if __name__ == '__main__':
    main()
