// "Heartbeat" waveform (Section 10A.9). Draws the wearable's real pulse wave when the
// finger is on and `ppg` arrives; otherwise a synthetic PQRST trace (sum of Gaussians) at
// the current BPM. It is only a visual: never stored, never classified.

const WAVES = [
  { a: 0.12, mu: 0.18, sigma: 0.025 },   // P
  { a: -0.14, mu: 0.285, sigma: 0.009 }, // Q
  { a: 1.0, mu: 0.3, sigma: 0.011 },     // R
  { a: -0.22, mu: 0.318, sigma: 0.01 },  // S
  { a: 0.28, mu: 0.52, sigma: 0.045 },   // T
];

export function pqrst(phase) {
  let value = 0;
  for (const wave of WAVES) value += wave.a * Math.exp(-((phase - wave.mu) ** 2) / (2 * wave.sigma ** 2));
  return value;
}

export function createHeartbeat(canvas, { color = '#FF4D6D', reducedMotion = false } = {}) {
  const ctx = canvas.getContext('2d');
  const history = [];
  const ppgQueue = [];
  let bpm = 72;
  let usePpg = false;
  let phase = 0;
  let lastTime = performance.now();
  let raf = 0;
  let wander = 0;

  const resize = () => {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(canvas.clientWidth * ratio);
    canvas.height = Math.round(canvas.clientHeight * ratio);
  };
  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  resize();

  const draw = () => {
    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);
    if (history.length < 2) return;
    const step = width / 600;
    const startX = width - history.length * step;
    const gradient = ctx.createLinearGradient(startX, 0, width, 0);
    gradient.addColorStop(0, 'rgba(255,255,255,0.05)');
    gradient.addColorStop(0.5, 'rgba(255,255,255,0.35)');
    gradient.addColorStop(1, color);
    ctx.strokeStyle = gradient;
    ctx.lineWidth = Math.max(1.5, width / 700);
    ctx.lineJoin = 'round';
    ctx.beginPath();
    history.forEach((value, index) => {
      const x = startX + index * step;
      const y = height * 0.62 - value * height * 0.42;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    const lastY = height * 0.62 - history[history.length - 1] * height * 0.42;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(width - 4, lastY, Math.max(3, width / 300), 0, Math.PI * 2);
    ctx.fill();
  };

  const tick = (now) => {
    raf = requestAnimationFrame(tick);
    const dt = Math.min(0.1, (now - lastTime) / 1000);
    lastTime = now;
    const samples = Math.max(1, Math.round(dt * 120));
    for (let i = 0; i < samples; i += 1) {
      if (usePpg && ppgQueue.length) {
        history.push(ppgQueue.shift());
      } else {
        phase = (phase + (bpm / 60) / 120) % 1;
        wander += (Math.random() - 0.5) * 0.002;
        wander *= 0.995;
        history.push(pqrst(phase) + wander);
      }
    }
    while (history.length > 600) history.shift();
    draw();
  };

  if (reducedMotion) {
    for (let i = 0; i < 600; i += 1) history.push(pqrst((i / 120) * (bpm / 60) % 1));
    draw();
  } else {
    raf = requestAnimationFrame(tick);
  }

  return {
    setBpm(value) {
      if (value && value > 20 && value < 240) bpm = value;
    },
    pushPpg(points) {
      if (!points || !points.length) {
        usePpg = false;
        return;
      }
      usePpg = true;
      const max = Math.max(...points.map(Math.abs)) || 1;
      // 25 points per second, stretched to the 120 Hz drawing rate.
      for (const value of points) {
        for (let k = 0; k < 5; k += 1) ppgQueue.push((value / max) * 0.8);
      }
      while (ppgQueue.length > 600) ppgQueue.shift();
    },
    stop() {
      cancelAnimationFrame(raf);
      observer.disconnect();
    },
  };
}
