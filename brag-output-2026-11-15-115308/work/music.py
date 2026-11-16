"""Score for the all-modules reel: 120 BPM, D minor, 30.5 s (61 beats). Music and effects are one
piece: every event is snapped to the 16th grid from frame 0, effects are pitched to the key, and
everything shares one reverb. Writes a 48 kHz stereo 16-bit WAV."""
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000
BEAT = 0.5
S16 = BEAT / 4
DUR = 30.5
N = int(DUR * SR)
rng = np.random.default_rng(11)
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else 'audio/score.wav')

CUTS = [3.0, 5.5, 8.0, 10.5, 13.0, 15.5, 19.5, 22.0, 24.5, 27.0]
DROP, NOVA, NOVA_END, OUTRO = 5.5, 15.5, 19.5, 27.0


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def grid(t):
    return round(t / S16) * S16


def smooth(x, n):
    if n <= 1:
        return x
    return np.convolve(x, np.ones(n) / n, mode='same')


def env(n, a, r, sus=1.0):
    e = np.full(n, sus)
    na, nr = int(a * SR), int(r * SR)
    if na:
        e[:na] = np.linspace(0, sus, na) ** 1.5
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr) ** 2
    return e


class Bus:
    def __init__(self):
        self.dry = np.zeros((N, 2))
        self.send = np.zeros((N, 2))

    def add(self, sig, t, gain=1.0, pan=0.0, rev=0.2):
        i = int(round(t * SR))
        if i >= N or i < 0:
            return
        sig = sig[: N - i]
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        st = np.stack([sig * l, sig * r], axis=1) * gain
        self.dry[i:i + len(sig)] += st
        self.send[i:i + len(sig)] += st * rev


mix = Bus()

# ── Harmony: one change per module cut ──────────────────────────────────────────
CHORDS = [
    (0.0, [50, 57, 62, 64, 65], 38),    # hook: Dm(add9)
    (3.0, [46, 53, 57, 62, 65], 34),    # reveal: Bbmaj7
    (5.5, [50, 57, 62, 65, 69], 38),    # heart: Dm
    (8.0, [46, 53, 58, 62, 65], 34),    # bones: Bb
    (10.5, [41, 53, 57, 60, 64], 41),   # mind: F(add9)
    (13.0, [48, 55, 60, 62, 67], 36),   # twin: C(sus2)
    (15.5, [50, 57, 62, 65, 69], 38),   # nova: Dm
    (17.5, [46, 53, 58, 62, 65], 34),   # nova: Bb
    (19.5, [41, 53, 57, 60, 65], 41),   # history: F
    (22.0, [43, 55, 58, 62, 67], 43),   # alerts: Gm
    (23.5, [45, 52, 57, 61, 64], 45),   # alerts: A (tension)
    (24.5, [46, 53, 58, 62, 65], 34),   # mc: Bb
    (25.75, [48, 55, 60, 64, 67], 36),  # mc: C
    (27.0, [38, 50, 57, 62, 64, 65], 38),  # outro: Dm(add9), home
]


def chord_at(t):
    k = 0
    for i, (s, _, _) in enumerate(CHORDS):
        if t >= s - 1e-9:
            k = i
    return k


def pad_note(f, dur, bright):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.zeros(n)
    for det in (-0.0045, 0.0, 0.0052):
        for h in range(1, 8):
            s += (1 / h) * np.exp(-(h - 1) * (0.55 / bright)) * np.sin(2 * np.pi * f * (1 + det) * h * t + rng.uniform(0, 6.28))
    return s * (1 + 0.08 * np.sin(2 * np.pi * 0.23 * t)) / 6


pad = np.zeros((N, 2))
for k, (start, notes, _) in enumerate(CHORDS):
    end = CHORDS[k + 1][0] if k + 1 < len(CHORDS) else DUR
    dur = end - start + 0.8
    bright = 0.7 if start < 3.0 else (1.25 if start >= OUTRO else 1.0)
    for j, m in enumerate(notes):
        s = pad_note(hz(m), dur, bright) * env(int(dur * SR), 1.0 if k == 0 else 0.25, 0.8)
        i = int(start * SR)
        s = s[: N - i]
        pan = (j / max(1, len(notes) - 1) - 0.5) * 0.7
        pad[i:i + len(s), 0] += s * np.cos((pan + 1) * np.pi / 4)
        pad[i:i + len(s), 1] += s * np.sin((pan + 1) * np.pi / 4)
fo = int(1.8 * SR)
pad[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 2

# ── Drums ──────────────────────────────────────────────────────────────────────
duck = np.ones(N)


def kick(level=1.0):
    n = int(0.4 * SR)
    t = np.arange(n) / SR
    f = 44 + 76 * np.exp(-t * 30)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    click = smooth(rng.standard_normal(n), 6) * np.exp(-t * 300) * 0.22
    return (body + click) * level


def hat(level, length=0.05):
    n = int(length * SR)
    x = rng.standard_normal(n)
    x = x - smooth(x, 4)
    return x * np.exp(-np.arange(n) / SR * 95) * level


def clap(level):
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n)
    band = smooth(x, 3) - smooth(x, 14)
    e = np.exp(-t * 26) + 0.5 * np.exp(-np.maximum(0, t - 0.012) * 40) * (t > 0.012)
    return band * e * level


def put_kick(t, level, depth=0.4):
    tt = grid(t)
    mix.add(kick(level), tt, gain=0.9, rev=0.04)
    i = int(tt * SR)
    n = int(0.3 * SR)
    shape = 1 - depth * np.exp(-np.arange(n) / SR * 12)
    seg = duck[i:i + n]
    duck[i:i + len(seg)] = np.minimum(seg, shape[: len(seg)])


def beats(a, b, step=BEAT):
    t = a
    while t < b - 1e-9:
        yield t
        t += step


for t in beats(DROP, OUTRO):
    in_nova = NOVA <= t < NOVA_END
    if in_nova and (round(t / BEAT) % 2 == 1):
        continue  # half-time under Dr. NOVA so the answer can be read
    put_kick(t, 0.75 if in_nova else 0.95)
for t in beats(DROP, OUTRO):
    in_nova = NOVA <= t < NOVA_END
    mix.add(hat(0.07 if in_nova else 0.13), grid(t + BEAT / 2), pan=0.25, rev=0.12)
    if not in_nova:
        mix.add(hat(0.05, 0.03), grid(t + BEAT * 0.25), pan=-0.25, rev=0.1)
        mix.add(hat(0.05, 0.03), grid(t + BEAT * 0.75), pan=-0.25, rev=0.1)
for t in beats(DROP + BEAT, OUTRO, BEAT * 2):  # claps on 2 and 4
    if NOVA <= t < NOVA_END:
        continue
    mix.add(clap(0.16), grid(t), pan=0.05, rev=0.3)

# Reveal build: quiet heartbeat kick, then a 16th roll of soft hats into the drop.
for t in (3.0, 3.25, 4.0, 4.25):
    put_kick(t, 0.6, 0.2)
for i, t in enumerate(beats(4.5, DROP, S16)):
    mix.add(hat(0.03 + 0.012 * i, 0.04), grid(t), pan=0.0, rev=0.25)

# ── Bass: 8ths on the root with an octave bounce ───────────────────────────────
def bass(m, length, level):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = np.sin(2 * np.pi * f * t) + 0.32 * np.sin(4 * np.pi * f * t) + 0.1 * np.sin(6 * np.pi * f * t)
    return s * env(n, 0.005, length * 0.6) * level


for i, t in enumerate(beats(DROP, OUTRO, BEAT / 2)):
    root = CHORDS[chord_at(t)][2]
    in_nova = NOVA <= t < NOVA_END
    m = root + (12 if i % 4 == 3 and not in_nova else 0)
    mix.add(bass(m, 0.2, 0.2 if in_nova else 0.27), grid(t), rev=0.02)
n = int(3.0 * SR)
tt = np.arange(n) / SR
mix.add(np.sin(2 * np.pi * hz(38) * tt) * env(n, 1.4, 1.0) * 0.3, 0.0, rev=0.0)

# ── Pluck arp: 16ths through the chord, from the drop ──────────────────────────
def pluck(m, level):
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = np.sin(2 * np.pi * f * t) * np.exp(-t * 16) + 0.35 * np.sin(4 * np.pi * f * t) * np.exp(-t * 26)
    return s * np.minimum(1, t / 0.002) * level


PATTERN = [0, 2, 1, 3, 2, 4, 3, 2]
for i, t in enumerate(beats(DROP, OUTRO, S16)):
    notes = CHORDS[chord_at(t)][1]
    tones = sorted(set(n + 12 for n in notes[1:]))
    m = tones[PATTERN[i % 8] % len(tones)]
    in_nova = NOVA <= t < NOVA_END
    lvl = 0.035 if in_nova else 0.05
    lvl *= 1.25 if i % 4 == 0 else 1.0
    mix.add(pluck(m, lvl), grid(t), pan=0.35 * np.sin(i * 0.7), rev=0.35)

# ── Bells ──────────────────────────────────────────────────────────────────────
def bell(m, level, length=1.6):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = (np.sin(2 * np.pi * f * t) * np.exp(-t * 3.2) + 0.4 * np.sin(4 * np.pi * f * t) * np.exp(-t * 5)
         + 0.16 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t * 8))
    return s * np.minimum(1, t / 0.004) * level


for i, m in enumerate([74, 77, 81, 76, 74]):
    mix.add(bell(m, 0.1), grid(0.5 + i * BEAT), pan=(-0.4 if i % 2 else 0.4), rev=0.55)
for i, m in enumerate([86, 81, 77, 74]):
    mix.add(bell(m, 0.12 - i * 0.015, 2.4), grid(OUTRO + 0.5 + i * BEAT), pan=(0.35 if i % 2 else -0.35), rev=0.6)

# ── Impacts, risers, whooshes ──────────────────────────────────────────────────
def boom(level, length=2.4):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = 30 + 45 * np.exp(-t * 6)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.2)
    return (s + smooth(rng.standard_normal(n), 40) * np.exp(-t * 7) * 0.6) * level


def whoosh(length, level, center=587.3):
    n = int(length * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n)
    w = max(2, int(SR / (center * 2)))
    band = smooth(x, w) - smooth(x, w * 6)
    shape = (t / length) ** 2.4 * np.clip((length - t) / 0.02, 0, 1)
    return band * shape * level


def riser(length, level):
    n = int(length * SR)
    t = np.arange(n) / SR
    p = t / length
    f = hz(50) * 2 ** (2 * p)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = rng.standard_normal(n)
    s = (0.4 * np.sin(ph) + 0.12 * np.sin(2 * ph) + 0.8 * (smooth(x, 3) - smooth(x, 30))) * p ** 2.2
    return s * np.clip((n - np.arange(n)) / (0.02 * SR), 0, 1) * level


mix.add(boom(0.5), 0.0, rev=0.25)
mix.add(boom(0.7), 3.0, rev=0.3)
mix.add(boom(0.6, 1.6), DROP, rev=0.2)
mix.add(boom(0.95, 3.2), OUTRO, rev=0.35)
mix.add(riser(1.0, 0.1), 4.5, rev=0.4)
mix.add(riser(1.5, 0.12), OUTRO - 1.5, rev=0.4)
for cut in CUTS:
    if cut in (3.0, DROP, OUTRO):
        continue
    mix.add(whoosh(0.25, 0.12), cut - 0.25, rev=0.35)

# ── UI sounds, pitched to D, under the music ───────────────────────────────────
def tick(m, level):
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * hz(m) * t) * np.exp(-t * 70) * level


mix.add(tick(86, 0.05), grid(8.0 + 0.75), rev=0.3)    # bones: rep
mix.add(tick(86, 0.05), grid(8.0 + 1.75), rev=0.3)
mix.add(tick(74, 0.1) + tick(86, 0.035), grid(13.0 + 1.0), rev=0.35)  # twin: tap
for k, t in enumerate(beats(NOVA + 0.375, NOVA + 1.25, S16)):  # nova: typing
    mix.add(tick([86, 88, 84, 89][k % 4], 0.02), grid(t), pan=0.15 * ((k % 3) - 1), rev=0.15)
mix.add(tick(74, 0.1) + tick(81, 0.04), grid(NOVA + 1.3), rev=0.35)  # send
mix.add(bell(81, 0.06), grid(NOVA + 1.75), pan=0.3, rev=0.6)        # answer lands
for k, t in enumerate(beats(19.75, 20.75, S16)):  # history: cells pop
    mix.add(tick([81, 84, 86, 89][k % 4], 0.012), grid(t), pan=-0.3 + 0.075 * k, rev=0.3)
mix.add(tick(74, 0.1) + tick(86, 0.035), grid(19.5 + 1.6), rev=0.35)  # Downlink tap
for t in (22.0, 22.5, 23.0, 23.5, 24.0):  # alerts: soft two-tone, on the glow pulse
    mix.add(bell(81 if round(t / BEAT) % 2 == 0 else 76, 0.045, 0.6), t, pan=0.0, rev=0.35)
for i in range(3):  # mission control: cards land
    mix.add(tick([69, 72, 76][i], 0.06), grid(24.5 + 0.3 + i * 0.125), pan=-0.4 + 0.4 * i, rev=0.35)

# ── Reverb and mix ─────────────────────────────────────────────────────────────
def ir(seconds=2.6, decay=0.75, seed=0):
    g = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    x = smooth(g.standard_normal(n) * np.exp(-t * (6.9 / (decay * 3))), 5)
    x[: int(0.012 * SR)] = 0
    return x / np.sqrt(np.sum(x ** 2))


def fft_conv(a, b):
    size = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    return np.fft.irfft(np.fft.rfft(a, size) * np.fft.rfft(b, size), size)[: len(a)]


wet = np.zeros((N, 2))
for c, seed in ((0, 1), (1, 2)):
    wet[:, c] = fft_conv(mix.send[:, c] + pad[:, c] * 0.35, ir(seed=seed))

song = mix.dry + pad * 0.4 * duck[:, None] + wet * 0.5
for c in range(2):
    song[:, c] = 0.85 * song[:, c] + 0.15 * smooth(song[:, c], 3)
fi = int(0.01 * SR)
song[:fi] *= np.linspace(0, 1, fi)[:, None]
fo = int(1.2 * SR)
song[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
song *= 0.12 / np.sqrt(np.mean(song ** 2))
song = np.tanh(song * 1.1) / 1.1
song *= 0.89 / np.max(np.abs(song))

OUT.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(OUT), 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((np.clip(song, -1, 1) * 32767).astype('<i2').tobytes())
print(f'wrote {OUT} {DUR}s')
