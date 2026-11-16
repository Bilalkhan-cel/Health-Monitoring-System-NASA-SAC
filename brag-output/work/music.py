"""Score for the AstroVital video: 120 BPM, D minor, 24.5 s. Music and effects are one piece:
every event sits on the 16th-note grid counted from frame 0, effects are pitched to the key,
and everything shares one reverb. Writes work/audio/score.wav (48 kHz stereo, 16-bit)."""
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000
BPM = 120
BEAT = 60 / BPM          # 0.5 s
S16 = BEAT / 4           # 0.125 s
DUR = 24.5
N = int(DUR * SR)
rng = np.random.default_rng(7)
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else 'audio/score.wav')


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def grid(t):
    """Snap a time to the 16th grid so nothing flams."""
    return round(t / S16) * S16


def env_adsr(n, a, r, sus=1.0):
    e = np.full(n, sus)
    na, nr = int(a * SR), int(r * SR)
    if na:
        e[:na] = np.linspace(0, sus, na) ** 1.5
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr) ** 2
    return e


def smooth(x, n):
    """Moving average (a gentle low-pass)."""
    if n <= 1:
        return x
    k = np.ones(n) / n
    return np.convolve(x, k, mode='same')


class Bus:
    def __init__(self):
        self.dry = np.zeros((N, 2))
        self.send = np.zeros((N, 2))

    def add(self, sig, t, gain=1.0, pan=0.0, rev=0.2):
        i = int(round(t * SR))
        if i >= N:
            return
        sig = sig[: N - i]
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        st = np.stack([sig * l, sig * r], axis=1) * gain
        self.dry[i:i + len(sig)] += st
        self.send[i:i + len(sig)] += st * rev


mix = Bus()

# ── Harmony: changes land on scene cuts (all on beats) ─────────────────────────
# D minor: i, VI, III, VII, i, VI, III, VII, V, i
CHORDS = [
    (0.0, [50, 57, 62, 64, 65]),      # Dm(add9)
    (3.5, [46, 53, 57, 62, 65]),      # Bbmaj7
    (7.0, [41, 53, 57, 60, 64]),      # F(add9)
    (9.0, [48, 55, 60, 62, 64]),      # C(add9)
    (11.5, [50, 57, 62, 65, 69]),     # Dm
    (13.5, [46, 53, 58, 62, 65]),     # Bb
    (15.5, [41, 53, 57, 60, 65]),     # F
    (18.0, [48, 55, 60, 64, 67]),     # C
    (19.5, [45, 52, 57, 61, 64]),     # A (dominant, lift)
    (21.0, [38, 50, 57, 62, 64, 65]), # Dm(add9), home
]
ROOTS = [38, 34, 41, 36, 38, 34, 41, 36, 33, 38]


def chord_at(t):
    idx = 0
    for k, (start, _) in enumerate(CHORDS):
        if t >= start:
            idx = k
    return idx


def pad_note(f, dur, bright=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for det in (-0.0045, 0.0, 0.0052):  # three detuned voices
        ff = f * (1 + det)
        for h in range(1, 9):
            amp = (1 / h) * np.exp(-(h - 1) * (0.55 / bright))
            sig += amp * np.sin(2 * np.pi * ff * h * t + rng.uniform(0, 6.28))
    vib = 1 + 0.08 * np.sin(2 * np.pi * 0.23 * t + rng.uniform(0, 6.28))
    return sig * vib / 6


pad = np.zeros((N, 2))
for k, (start, notes) in enumerate(CHORDS):
    end = CHORDS[k + 1][0] if k + 1 < len(CHORDS) else DUR
    dur = end - start + 0.9
    bright = 0.7 if start < 3.5 else (1.3 if start >= 21.0 else 1.0)
    for j, m in enumerate(notes):
        s = pad_note(hz(m), dur, bright) * env_adsr(int(dur * SR), 0.35 if k else 1.2, 0.9)
        i = int(start * SR)
        s = s[: N - i]
        pan = (j / max(1, len(notes) - 1) - 0.5) * 0.7
        pad[i:i + len(s), 0] += s * np.cos((pan + 1) * np.pi / 4)
        pad[i:i + len(s), 1] += s * np.sin((pan + 1) * np.pi / 4)
# Fade the pad out at the very end.
tail = int(1.6 * SR)
pad[-tail:] *= np.linspace(1, 0, tail)[:, None] ** 2

# ── Drums: a heartbeat kick (lub-dub) that becomes a steady pulse ───────────────
def kick(level=1.0, length=0.42, f0=110, f1=42):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 9)
    click = smooth(rng.standard_normal(n), 6) * np.exp(-t * 320) * 0.25
    return (body + click) * level


def hat(level=1.0, length=0.05):
    n = int(length * SR)
    x = rng.standard_normal(n)
    x = x - smooth(x, 4)  # crude high-pass
    return x * np.exp(-np.arange(n) / SR * 90) * level


duck = np.ones(N)  # pad side-chain, so the pulse breathes


def hit_kick(t, level, dub=False):
    tt = grid(t)
    mix.add(kick(level * (0.62 if dub else 1.0)), tt, gain=0.9, rev=0.05)
    i = int(tt * SR)
    n = int(0.32 * SR)
    shape = 1 - (0.38 if not dub else 0.2) * np.exp(-np.arange(n) / SR * 11)
    seg = duck[i:i + n]
    duck[i:i + len(seg)] = np.minimum(seg, shape[: len(seg)])


# Heartbeat from the reveal through Today: lub on the beat, dub a 16th later... every 2 beats.
t = 3.5
while t < 11.5 - 1e-9:
    hit_kick(t, 0.95)
    hit_kick(t + S16 * 2, 0.95, dub=True)
    t += BEAT * 2
# Dr. NOVA: heartbeat continues, softer, a little sparser under the typing.
t = 11.5
while t < 18.0 - 1e-9:
    hit_kick(t, 0.75)
    hit_kick(t + S16 * 2, 0.75, dub=True)
    t += BEAT * 2
# Mission Control: four on the floor into the lift.
t = 18.0
while t < 21.0 - 1e-9:
    hit_kick(t, 0.9)
    t += BEAT
# Hats from Today: off-beat 8ths, quiet, with a 16th pickup now and then.
t = 7.0
while t < 21.0 - 1e-9:
    mix.add(hat(0.16), grid(t + BEAT / 2), pan=0.25, rev=0.15)
    if int(round(t / BEAT)) % 4 == 3:
        mix.add(hat(0.09), grid(t + BEAT * 0.75), pan=-0.2, rev=0.15)
    t += BEAT

# ── Bass: soft 8th-note pulse on the root, from Today ──────────────────────────
def bass_note(m, length, level):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.12 * np.sin(2 * np.pi * 3 * f * t)
    return s * env_adsr(n, 0.006, length * 0.6) * level


t = 7.0
while t < 21.0 - 1e-9:
    k = chord_at(t)
    m = ROOTS[k]
    first = abs((t / BEAT) - round(t / BEAT)) < 1e-6
    mix.add(bass_note(m, 0.22, 0.30 if first else 0.2), grid(t), rev=0.03)
    t += BEAT / 2
# Sub swell under the hook.
n = int(3.5 * SR)
tt = np.arange(n) / SR
mix.add(np.sin(2 * np.pi * hz(38) * tt) * env_adsr(n, 1.5, 1.2) * 0.32, 0.0, rev=0.0)

# ── Bells: sparse arpeggio of chord tones, high, in the hook and the outro ──────
def bell(m, level=1.0, length=1.6):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = (np.sin(2 * np.pi * f * t) * np.exp(-t * 3.2)
         + 0.4 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * 5)
         + 0.18 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t * 8))
    att = np.minimum(1, t / 0.004)
    return s * att * level


hook_arp = [74, 77, 81, 76, 74, 81, 77, 76]  # D F A E ...
for i, m in enumerate(hook_arp[:6]):
    mix.add(bell(m, 0.10), grid(0.5 + i * BEAT), pan=(-0.4 if i % 2 else 0.4), rev=0.55)
# NOVA "thinking" → "speaking": two soft rising bells as the answer lands.
mix.add(bell(81, 0.07), grid(11.5 + 1.75), pan=0.3, rev=0.6)
mix.add(bell(86, 0.08), grid(11.5 + 2.375), pan=-0.3, rev=0.6)
# Outro: a slow descending figure over the home chord.
for i, m in enumerate([86, 81, 77, 74]):
    mix.add(bell(m, 0.12 - i * 0.015, 2.4), grid(21.0 + 0.5 + i * BEAT), pan=(0.35 if i % 2 else -0.35), rev=0.6)

# ── Impacts, risers and whooshes (pitched to D, sent to the same reverb) ────────
def boom(level=1.0, length=2.4):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = 30 + 45 * np.exp(-t * 6)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.2)
    noise = smooth(rng.standard_normal(n), 40) * np.exp(-t * 7) * 0.6
    return (s + noise) * level


def whoosh(length, level, center=587.3):
    """Noise swell ending exactly on the cut, band-limited around D5."""
    n = int(length * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n)
    w = max(2, int(SR / (center * 2)))
    band = smooth(x, w) - smooth(x, w * 6)
    shape = (t / length) ** 2.4
    shape *= np.clip((length - t) / 0.03, 0, 1)
    return band * shape * level


def riser(start, end, level):
    n = int((end - start) * SR)
    t = np.arange(n) / SR
    p = t / (end - start)
    f = hz(50) * 2 ** (2 * p)  # D3 → D5
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    x = rng.standard_normal(n)
    noise = smooth(x, 3) - smooth(x, 30)
    s = (tone * 0.4 + noise * 0.8) * p ** 2.2
    s *= np.clip((n - np.arange(n)) / (0.02 * SR), 0, 1)
    return s * level


mix.add(boom(0.55), 0.0, rev=0.25)
mix.add(boom(0.75), 3.5, rev=0.3)
mix.add(boom(0.95, 3.2), 21.0, rev=0.35)
for cut in (7.0, 11.5, 18.0):
    w = whoosh(0.5, 0.22)
    mix.add(w, cut - 0.5, pan=0.0, rev=0.4)
w = whoosh(0.9, 0.18)
mix.add(w, 3.5 - 0.9, rev=0.5)
r = riser(19.0, 21.0, 0.16)
mix.add(r, 19.0, rev=0.4)

# ── UI sounds: tiny pitched ticks, under the music ─────────────────────────────
def tick(m, level=1.0):
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * hz(m) * t) * np.exp(-t * 70) * level


# Today: score cards count up (4 cards, 16ths), then the tap on Heart.
for i in range(4):
    mix.add(tick(81 + [0, 3, 7, 12][i], 0.05), grid(7.0 + 0.25 + i * S16), pan=-0.3 + i * 0.2, rev=0.3)
mix.add(tick(74, 0.12) + tick(86, 0.04), grid(7.0 + 2.6), rev=0.35)
# Dr. NOVA: typing on 16ths, then send.
t = 11.5 + 0.25
k = 0
while t < 11.5 + 1.35:
    mix.add(tick([86, 88, 84, 89][k % 4], 0.022), grid(t), pan=0.15 * ((k % 3) - 1), rev=0.15)
    t += S16
    k += 1
mix.add(tick(74, 0.12) + tick(81, 0.05), grid(11.5 + 1.55), rev=0.35)
# Mission Control: crew cards land.
for i in range(3):
    mix.add(tick([69, 72, 76][i], 0.07), grid(18.0 + 0.5 + i * 0.16), pan=-0.4 + i * 0.4, rev=0.35)

# ── Reverb: one shared space ───────────────────────────────────────────────────
def ir(seconds=2.6, decay=0.75, seed=0):
    g = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    x = g.standard_normal(n) * np.exp(-t * (6.9 / (decay * 3)))
    x = smooth(x, 5)
    x[: int(0.012 * SR)] = 0  # pre-delay
    return x / np.sqrt(np.sum(x ** 2))


def fft_conv(a, b):
    size = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    out = np.fft.irfft(np.fft.rfft(a, size) * np.fft.rfft(b, size), size)
    return out[: len(a)]


wet = np.zeros((N, 2))
pad_send = pad * 0.35
for c, seed in ((0, 1), (1, 2)):
    wet[:, c] = fft_conv(mix.send[:, c] + pad_send[:, c], ir(seed=seed))

# ── Mix ────────────────────────────────────────────────────────────────────────
song = mix.dry + pad * 0.42 * duck[:, None] + wet * 0.55
# Gentle low-shelf cleanup on the very top: soften harshness.
for c in range(2):
    song[:, c] = 0.85 * song[:, c] + 0.15 * smooth(song[:, c], 3)
# Short fade-in on the first frame to avoid a click, longer fade at the end.
fi = int(0.01 * SR)
song[:fi] *= np.linspace(0, 1, fi)[:, None]
fo = int(1.2 * SR)
song[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5

# Loudness: set RMS, soft-clip peaks, ceiling at -1 dBFS.
rms = np.sqrt(np.mean(song ** 2))
song *= 0.12 / rms
song = np.tanh(song * 1.1) / 1.1
peak = np.max(np.abs(song))
song *= 0.89 / peak

OUT.parent.mkdir(parents=True, exist_ok=True)
pcm = (np.clip(song, -1, 1) * 32767).astype('<i2')
with wave.open(str(OUT), 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print(f'wrote {OUT} {DUR}s rms={np.sqrt(np.mean(song**2)):.3f} peak={np.max(np.abs(song)):.3f}')
