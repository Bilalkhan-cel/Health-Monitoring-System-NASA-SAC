import sys, wave
import numpy as np
from PIL import Image, ImageDraw
w = wave.open(sys.argv[1]); sr = w.getframerate()
x = np.frombuffer(w.readframes(w.getnframes()), '<i2').reshape(-1, 2).mean(1) / 32768
hop, win = 512, 4096
frames = [x[i:i+win] * np.hanning(win) for i in range(0, len(x) - win, hop)]
S = np.abs(np.fft.rfft(frames, axis=1)).T
freqs = np.fft.rfftfreq(win, 1/sr)
# log-frequency rows 30 Hz .. 16 kHz
rows = np.geomspace(30, 16000, 300)
idx = np.searchsorted(freqs, rows)
img = 20*np.log10(S[idx] + 1e-6); img = np.clip((img + 60) / 70, 0, 1)[::-1]
im = Image.fromarray((img*255).astype('uint8')).resize((1470, 300))
W = 1470; canvas = Image.new('L', (W, 420), 0); canvas.paste(im, (0, 0))
d = ImageDraw.Draw(canvas)
env = np.array([np.sqrt(np.mean(x[i:i+sr//60]**2)) for i in range(0, len(x), sr//60)])
for i, v in enumerate(env):
    X = int(i / len(env) * W); d.line([(X, 420), (X, 420 - int(v*300))], fill=200)
for s in (3.5, 7, 11.5, 18, 21):
    X = int(s / (len(x)/sr) * W); d.line([(X, 0), (X, 420)], fill=255)
canvas.save(sys.argv[2])
for a, b in ((0,3.5),(3.5,7),(7,11.5),(11.5,18),(18,21),(21,24.5)):
    seg = x[int(a*sr):int(b*sr)]
    print(f'{a:5}-{b:5}: rms {20*np.log10(np.sqrt(np.mean(seg**2))):6.1f} dB  peak {20*np.log10(np.max(np.abs(seg))):6.1f}')
