// AstroVital technical deck: 7 slides for judges. Big type, every technical detail named,
// no screenshots except the title. Structured deck: theme, layouts, placeholders, sections.
const path = require('path');
const pptxgen = require('pptxgenjs');
const { applyTheme } = require('./apply_theme.js');

const IMG = (n) => path.join(__dirname, 'frames', n);
const OUT = path.join(__dirname, '..', 'AstroVital-overview.pptx');

const THEME = {
  name: 'AstroVital',
  headFontFace: 'Arial',
  bodyFontFace: 'Arial',
  colors: {
    dk1: '05070A', lt1: 'F2F4F7', dk2: '0E1117', lt2: 'A3ABB8',
    accent1: '7CF3FF', accent2: '2EE59D', accent3: '3B9EFF', accent4: 'FFC53D', accent5: 'FF4D6D', accent6: '9C8CFF',
    hlink: '7CF3FF', folHlink: '9C8CFF',
  },
};
const BG = '05070A';
const CARD_LINE = '2A303B';
const MONO = 'Courier New';

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.333 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = 'AstroVital: technical overview';
pres.subject = 'Crew health monitoring for long space missions';
pres.author = 'AstroVital';
const C = pres.SchemeColor;

const FOOT = 'AstroVital · prototype for educational purposes, not a certified medical device';

pres.defineSlideMaster({
  title: 'AV Title',
  background: { color: BG },
  objects: [{ text: { text: FOOT, options: { x: 0.6, y: 6.98, w: 9, h: 0.3, fontSize: 11, color: C.background2, margin: 0 } } }],
});
pres.defineSlideMaster({
  title: 'AV Content',
  background: { color: BG },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { text: { text: FOOT, options: { x: 0.6, y: 6.98, w: 9, h: 0.3, fontSize: 11, color: C.background2, margin: 0 } } },
    { placeholder: { options: { name: 'kicker', type: 'body', x: 0.9, y: 0.36, w: 9, h: 0.34, fontFace: MONO, fontSize: 14,
      bold: true, color: C.accent1, charSpacing: 1, margin: 0, valign: 'middle' }, text: '' } },
    { placeholder: { options: { name: 'title', type: 'title', x: 0.6, y: 0.72, w: 12.13, h: 0.8, fontSize: 36, bold: true,
      color: C.background1, margin: 0, valign: 'middle', align: 'left' }, text: '' } },
  ],
  slideNumber: { x: 12.23, y: 6.98, w: 0.5, h: 0.3, fontSize: 11, color: 'A3ABB8', align: 'right' },
});

// ── helpers ─────────────────────────────────────────────────────────────────
function dot(slide, x, y, color, size = 0.17, name = 'Status dot') {
  slide.addShape(pres.shapes.OVAL, { x, y, w: size, h: size, fill: { color }, line: { color, width: 0 }, objectName: name });
}
function header(slide, kicker, title, color) {
  dot(slide, 0.6, 0.445, color, 0.17, 'Kicker dot');
  slide.addText(kicker, { placeholder: 'kicker', color });
  slide.addText(title, { placeholder: 'title' });
}
function card(slide, x, y, w, h, name, fill) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: fill || C.text2 },
    line: { color: CARD_LINE, width: 1 }, objectName: name });
}
function heading(slide, x, y, w, text, color, size = 22) {
  dot(slide, x, y + 0.135, color, 0.17, `${text} dot`);
  slide.addText(text, { x: x + 0.3, y, w: w - 0.3, h: 0.44, fontSize: size, bold: true, color: C.background1, margin: 0,
    valign: 'middle', isTextBox: true, objectName: `${text} heading` });
}
// A spec row: small mono label over a big value line.
function spec(slide, x, y, w, labelText, value, color, { size = 18, h = 0.62 } = {}) {
  slide.addText(labelText, { x, y, w, h: 0.26, fontFace: MONO, fontSize: 13, bold: true, color, margin: 0, valign: 'middle',
    charSpacing: 1, isTextBox: true, objectName: `${labelText} label` });
  slide.addText(value, { x, y: y + 0.28, w, h, fontSize: size, color: C.background1, margin: 0, valign: 'top', isTextBox: true,
    objectName: `${labelText} value` });
}
function lines(slide, items, x, y, w, h, { size = 18, color, name = 'List', space = 6 } = {}) {
  slide.addText(items.map((t, i) => ({ text: t, options: { breakLine: i < items.length - 1 } })), {
    x, y, w, h, fontSize: size, color: color || C.background1, margin: 0, valign: 'top', paraSpaceAfter: space, isTextBox: true, objectName: name });
}
function arrow(slide, x, y, w, name) {
  slide.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color: C.background2, width: 2, endArrowType: 'triangle' }, objectName: name });
}
function formula(slide, x, y, w, h, title, expr, note, color) {
  card(slide, x, y, w, h, `${title} card`, '0B1220');
  slide.addText(title, { x: x + 0.3, y: y + 0.2, w: w - 0.6, h: 0.3, fontFace: MONO, fontSize: 13, bold: true, color, charSpacing: 1,
    margin: 0, isTextBox: true, objectName: `${title} label` });
  slide.addText(expr, { x: x + 0.3, y: y + 0.6, w: w - 0.6, h: h - 1.15, fontFace: MONO, fontSize: 16, bold: true, color: C.background1,
    margin: 0, valign: 'top', isTextBox: true, objectName: `${title} formula` });
  if (note) slide.addText(note, { x: x + 0.3, y: y + h - 0.55, w: w - 0.6, h: 0.4, fontSize: 15, color: C.background2, margin: 0,
    valign: 'middle', isTextBox: true, objectName: `${title} note` });
}
function badge(slide, x, y, n, color, fill) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: 0.44, h: 0.44, fill: { color: fill }, line: { color, width: 1.5 }, objectName: `Badge ${n}` });
  slide.addText(String(n), { x, y, w: 0.44, h: 0.44, fontSize: 16, bold: true, color, align: 'center', valign: 'middle', margin: 0,
    isTextBox: true, objectName: `Badge ${n} number` });
}
function logo(slide, cx, cy, s) {
  slide.addShape(pres.shapes.OVAL, { x: cx - 0.27 * s, y: cy - 0.27 * s, w: 0.54 * s, h: 0.54 * s, fill: { color: C.text1, transparency: 100 },
    line: { color: C.background1, width: 2.5 }, objectName: 'Logo planet' });
  slide.addShape(pres.shapes.OVAL, { x: cx - 0.5 * s, y: cy - 0.175 * s, w: 1.0 * s, h: 0.35 * s, fill: { color: C.text1, transparency: 100 },
    line: { color: C.accent1, width: 2 }, rotate: -24, objectName: 'Logo ring' });
  slide.addShape(pres.shapes.OVAL, { x: cx + 0.33 * s, y: cy - 0.27 * s, w: 0.13 * s, h: 0.13 * s, fill: { color: C.background1 },
    line: { color: C.background1, width: 0 }, objectName: 'Logo moon' });
}

// ── 1. Title ────────────────────────────────────────────────────────────────
pres.addSection({ title: 'Introduction' });
{
  const s = pres.addSlide({ masterName: 'AV Title', sectionTitle: 'Introduction' });
  s.addImage({ path: IMG('earth.png'), x: 0, y: 0, w: 13.333, h: 7.5, altText: 'The app\'s live 3D Earth with NASA\'s ISS model', objectName: 'Earth background' });
  logo(s, 6.667, 0.85, 1.0);
  s.addText('AstroVital', { x: 1.5, y: 1.3, w: 10.33, h: 1.0, fontSize: 60, bold: true, color: C.background1, align: 'center',
    valign: 'middle', margin: 0, isTextBox: true, objectName: 'Title' });
  s.addText('Crew health monitoring for long space missions', { x: 1.0, y: 2.3, w: 11.33, h: 0.55, fontSize: 26,
    color: C.background1, align: 'center', valign: 'middle', margin: 0, isTextBox: true, objectName: 'Subtitle' });
  s.addText('ESP32 wearable · Bluetooth LE · Computer vision · OpenAI Whisper · NLP models · AI flight doctor', {
    x: 0.8, y: 2.95, w: 11.73, h: 0.45, fontSize: 18, bold: true, color: C.accent1, align: 'center', valign: 'middle', margin: 0,
    isTextBox: true, objectName: 'Technology line' });
  s.addNotes('AstroVital monitors an astronaut\'s heart, bones and muscle, and mind with real sensors and on-device AI, and gives a plain answer for every number. This deck goes through each module\'s technology: the ESP32 wearable and Bluetooth for the heart, computer vision for exercise, OpenAI Whisper and NLP models for the mind, the Dr. NOVA AI doctor, and the ground segment.');
}

// ── 2. Architecture ─────────────────────────────────────────────────────────
pres.addSection({ title: 'System' });
{
  const s = pres.addSlide({ masterName: 'AV Content', sectionTitle: 'System' });
  header(s, '01 · SYSTEM ARCHITECTURE', 'Sense, process, think, show: on one computer', C.accent1);
  const cols = [
    ['Sense', C.accent5, ['ESP32 wearable', 'MAX30102 + DS18B20', 'Bluetooth LE strap', 'Webcam', 'Microphone']],
    ['Process', C.accent1, ['Flask 3 server', 'SQLite (WAL mode)', 'Live SSE stream', 'mDNS discovery', 'REST + WebSocket']],
    ['Think', C.accent2, ['MediaPipe Pose', 'OpenAI Whisper', 'RoBERTa sentiment', 'DistilRoBERTa emotion', 'Rules + AlertGate']],
    ['Show', C.accent3, ['Crew web app', '3D body twin', 'Dr. NOVA voice', 'Mission Control', 'Downlink PDF']],
  ];
  const w = 2.72;
  const gap = 0.415;
  cols.forEach(([name, col, items], i) => {
    const x = 0.6 + i * (w + gap);
    card(s, x, 1.85, w, 3.65, `${name} column`);
    heading(s, x + 0.25, 2.02, w - 0.4, name, col, 24);
    lines(s, items, x + 0.25, 2.65, w - 0.4, 2.75, { size: 18, name: `${name} items`, space: 8 });
    if (i < cols.length - 1) arrow(s, x + w + 0.05, 3.67, gap - 0.1, `${name} arrow`);
  });
  card(s, 0.6, 5.75, 12.13, 0.95, 'Offline-first note', '0B1220');
  s.addText([
    { text: 'Offline-first: ', options: { bold: true, color: C.accent1 } },
    { text: 'every sensor, model and database runs on this computer. Only Dr. NOVA\'s voice uses the cloud.', options: { color: C.background1 } },
  ], { x: 0.9, y: 5.75, w: 11.6, h: 0.95, fontSize: 20, margin: 0, valign: 'middle', isTextBox: true, objectName: 'Offline-first text' });
  s.addNotes('Four layers. Sense: the ESP32 wearable with the MAX30102 pulse-oximetry sensor and DS18B20 temperature probe, a Bluetooth LE chest strap, the webcam and the microphone. Process: a Flask 3 server with SQLite in WAL mode, a Server-Sent Events live stream, and mDNS so the wearable finds the server by itself. Think: MediaPipe pose, OpenAI Whisper, RoBERTa and DistilRoBERTa language models, and a rules engine with an AlertGate. Show: the crew web app, the 3D twin, the Dr. NOVA voice doctor, Mission Control and the Downlink PDF.');
}

// ── 3. Heart ────────────────────────────────────────────────────────────────
pres.addSection({ title: 'Modules' });
{
  const s = pres.addSlide({ masterName: 'AV Content', sectionTitle: 'Modules' });
  header(s, '02 · HEART MODULE', 'Heart: ESP32 wearable and Bluetooth', C.accent5);
  card(s, 0.6, 1.85, 6.0, 4.85, 'Wearable card');
  heading(s, 0.9, 2.0, 5.4, 'ESP32 wearable (custom firmware)', C.accent5);
  const L = [
    ['SENSOR', 'MAX30102 PPG, red + IR LEDs: heart rate + SpO₂'],
    ['SAMPLING', '100 Hz, 4× averaging, 411 µs pulse width'],
    ['TEMPERATURE', 'DS18B20 digital probe on the 1-Wire bus'],
    ['ON-CHIP SIGNAL PROCESSING', 'Finger detection, 5-point median filter, quality flags'],
    ['LINK', 'Wi-Fi JSON at 1 Hz, token, offline queue, mDNS'],
  ];
  L.forEach(([l, v], i) => spec(s, 0.9, 2.6 + i * 0.8, 5.45, l, v, C.accent5, { size: 17, h: 0.5 }));
  card(s, 6.85, 1.85, 5.88, 4.85, 'Pipeline card');
  heading(s, 7.15, 2.0, 5.3, 'Bluetooth and the live check', C.accent3);
  const R = [
    ['BLUETOOTH LE', 'Web Bluetooth strap, Heart Rate Service 0x180D'],
    ['LIVE STREAM', 'Server-Sent Events: live BPM + ECG-style trace'],
    ['PROTOCOL', '5-minute rest, then a 90-second measurement'],
    ['VITALS', 'HR, SpO₂, temp, BP, glucose, breathing rate'],
    ['ALERTGATE', 'Confirms critical readings before alerting'],
  ];
  R.forEach(([l, v], i) => spec(s, 7.15, 2.6 + i * 0.8, 5.35, l, v, C.accent3, { size: 17, h: 0.5 }));
  s.addNotes('The wearable is an ESP32 running our own PlatformIO firmware. The MAX30102 is an optical PPG sensor with red and infrared LEDs; we sample at 100 Hz with 4x averaging and a 411 microsecond pulse width. Temperature comes from a DS18B20 on the 1-Wire bus. On the chip we detect the finger with hysteresis, median-filter the values and flag poor signal; frames are sent as JSON once a second over Wi-Fi with a device token, queued offline with backoff, and the server is found by mDNS. A Bluetooth LE chest strap also works through Web Bluetooth on the standard Heart Rate Service (0x180D, measurement characteristic 0x2A37). Note for judges: blood pressure, glucose and breathing rate are generated for the demo because no sensor for them is attached.');
}

// ── 4. Bones & muscle ───────────────────────────────────────────────────────
{
  const s = pres.addSlide({ masterName: 'AV Content', sectionTitle: 'Modules' });
  header(s, '03 · BONES & MUSCLE MODULE', 'Bones & muscle: computer vision on the webcam', C.accent2);
  card(s, 0.6, 1.85, 6.0, 4.85, 'Vision pipeline card');
  heading(s, 0.9, 2.0, 5.4, 'Computer-vision pipeline', C.accent2);
  const steps = [
    'Webcam frame, in the browser',
    'MediaPipe Pose Landmarker (GPU)',
    '33 landmarks → 17 COCO keypoints',
    'Joint angles + EMA smoothing',
    'Rep state machine, ≥ 0.6 s per rep',
    'Live form cues and form score',
  ];
  steps.forEach((t, i) => {
    const y = 2.62 + i * 0.66;
    badge(s, 0.9, y, i + 1, C.accent2, '10261D');
    s.addText(t, { x: 1.5, y: y - 0.03, w: 4.9, h: 0.5, fontSize: 18, color: C.background1, margin: 0, valign: 'middle', isTextBox: true, objectName: `Step ${i + 1} text` });
  });
  card(s, 6.85, 1.85, 5.88, 2.3, 'Machines card');
  heading(s, 7.15, 2.0, 5.3, 'Space exercise machines', C.accent4);
  lines(s, [
    'ARED (resistive exercise device)',
    'Cycle ergometer',
    'Harnessed treadmill, cadence by camera',
  ], 7.15, 2.6, 5.35, 1.5, { size: 18, name: 'Machines list', space: 6 });
  formula(s, 6.85, 4.4, 5.88, 2.3, 'LOADING INDEX (LAST 7 DAYS)',
    '100 × (0.40·volume + 0.30·frequency\n     + 0.20·intensity + 0.10·form)',
    'Camera: squats, push-ups, pull-ups, running', C.accent2);
  s.addNotes('Bones and muscle use computer vision. MediaPipe Pose Landmarker runs in the browser on the GPU; its 33 landmarks are mapped to the 17 COCO keypoints, and only those keypoints reach the server, never video. The server computes joint angles, smooths them, and counts reps with small state machines with hysteresis and a minimum of 0.6 seconds per rep, then gives live form cues. In zero-g the crew logs the station\'s exercise machines: ARED, the cycle ergometer and the harnessed treadmill. Everything feeds the Musculoskeletal Loading Index over the last 7 days; intensity is measured in METs.');
}

// ── 5. Mind ─────────────────────────────────────────────────────────────────
{
  const s = pres.addSlide({ masterName: 'AV Content', sectionTitle: 'Modules' });
  header(s, '04 · MIND MODULE', 'Mind: OpenAI Whisper and NLP models', C.accent6);
  const flow = [
    ['Voice', 'browser mic'],
    ['Whisper', 'speech to text'],
    ['Safety screen', 'crisis rules, first'],
    ['NLP models', 'sentiment + emotion'],
    ['Wellbeing', 'score 0–100'],
  ];
  const fw = 2.15;
  const fg = 0.345;
  flow.forEach(([t, sub], i) => {
    const x = 0.6 + i * (fw + fg);
    card(s, x, 1.85, fw, 1.15, `${t} step`, '15122A');
    s.addText(t, { x: x + 0.1, y: 1.92, w: fw - 0.2, h: 0.5, fontSize: 20, bold: true, color: C.background1, align: 'center', valign: 'middle', margin: 0, isTextBox: true, objectName: `${t} step title` });
    s.addText(sub, { x: x + 0.1, y: 2.42, w: fw - 0.2, h: 0.45, fontSize: 15, color: C.background2, align: 'center', valign: 'middle', margin: 0, isTextBox: true, objectName: `${t} step sub` });
    if (i < flow.length - 1) arrow(s, x + fw + 0.04, 2.42, fg - 0.08, `${t} arrow`);
  });
  card(s, 0.6, 3.25, 7.1, 3.45, 'Models card');
  heading(s, 0.9, 3.4, 6.5, 'Models, all on this computer', C.accent6);
  spec(s, 0.9, 4.0, 6.6, 'SPEECH TO TEXT', 'OpenAI Whisper (base), faster-whisper, int8 CPU', C.accent6, { size: 17, h: 0.5 });
  spec(s, 0.9, 4.88, 6.6, 'SENTIMENT · ROBERTA', 'cardiffnlp/twitter-roberta-base-sentiment-latest', C.accent6, { size: 15, h: 0.5 });
  spec(s, 0.9, 5.76, 6.6, 'EMOTION · DISTILROBERTA, 7 CLASSES', 'j-hartmann/emotion-english-distilroberta-base', C.accent6, { size: 15, h: 0.5 });
  formula(s, 7.95, 3.25, 4.78, 3.45, 'MENTAL WELLBEING SCORE',
    '100 × (0.35·sentiment\n     + 0.25·emotion\n     + 0.20·self-rating\n     + 0.20·(1 − flags))',
    'Audio deleted once read', C.accent6);
  s.addNotes('The mind check-in is a short spoken conversation. The audio is transcribed on this computer by OpenAI\'s Whisper base model through faster-whisper, quantised to int8 on the CPU with voice-activity detection. A rule-based safety screen runs first and never depends on a model. Then two Hugging Face transformer models score each sentence: RoBERTa for sentiment and DistilRoBERTa for seven emotions. The Mental Wellbeing Score combines sentiment, emotional valence, the astronaut\'s own mood rating and a penalty for flagged themes. Audio is deleted once it is read; nothing goes to the cloud; it never diagnoses.');
}

// ── 6. Intelligence ─────────────────────────────────────────────────────────
pres.addSection({ title: 'Intelligence' });
{
  const s = pres.addSlide({ masterName: 'AV Content', sectionTitle: 'Intelligence' });
  header(s, '05 · AI DOCTOR AND SCORING', 'Dr. NOVA, readiness score and the 3D twin', C.accent3);
  card(s, 0.6, 1.85, 6.0, 4.85, 'Dr. NOVA card');
  heading(s, 0.9, 2.0, 5.4, 'Dr. NOVA: three-tier AI doctor', C.accent3);
  const tiers = [
    ['OpenHome voice agent', 'WebSocket: PCM16 16 kHz up, MP3 voice back'],
    ['Fallback LLM', 'OpenAI-compatible API if OpenHome is down'],
    ['Offline rules engine', 'Always answers, no network needed'],
  ];
  tiers.forEach(([t, d], i) => {
    const y = 2.62 + i * 1.0;
    badge(s, 0.9, y + 0.03, i + 1, C.accent3, '0E1B2E');
    s.addText(t, { x: 1.5, y, w: 4.9, h: 0.4, fontSize: 19, bold: true, color: C.background1, margin: 0, valign: 'middle', isTextBox: true, objectName: `Tier ${i + 1} title` });
    s.addText(d, { x: 1.5, y: y + 0.4, w: 4.9, h: 0.45, fontSize: 16, color: C.background2, margin: 0, valign: 'top', isTextBox: true, objectName: `Tier ${i + 1} detail` });
  });
  s.addText('Sees readings, trends and check-in summaries. Never the name or transcripts.', {
    x: 0.9, y: 5.68, w: 5.45, h: 0.85, fontSize: 16, color: C.accent1, margin: 0, valign: 'top', isTextBox: true, objectName: 'Context note' });
  formula(s, 6.85, 1.85, 5.88, 2.5, 'READINESS SCORE',
    'Σ(weight·system score) / Σ weight\ncritical → max 49\ncaution  → max 79',
    'Needs fresh data from 2+ systems', C.accent3);
  card(s, 6.85, 4.6, 5.88, 2.1, '3D card');
  heading(s, 7.15, 4.75, 5.3, '3D graphics: three.js, WebGL', C.accent1, 20);
  lines(s, [
    'Hologram twin: GLB model, custom shader',
    'Earth: GLSL day/night shader, NASA ISS',
  ], 7.15, 5.32, 5.35, 1.2, { size: 17, name: '3D list', space: 6 });
  s.addNotes('Dr. NOVA has three tiers. First the OpenHome voice agent over a WebSocket, sending 16 kHz PCM audio and receiving MP3 speech, with a custom Ability we built and expose through a tunnel. If OpenHome is unreachable it falls back to any OpenAI-compatible LLM, and with no network at all it uses an offline rules engine. It sees only the latest readings, trends and check-in summaries, never the astronaut\'s name or transcripts. The readiness score is a weighted mean of the system scores, capped at 49 if any reading is critical and 79 if any needs attention. The 3D body twin and Earth are three.js with custom GLSL shaders and NASA\'s ISS model.');
}

// ── 7. Ground, security, engineering ────────────────────────────────────────
pres.addSection({ title: 'Ground and engineering' });
{
  const s = pres.addSlide({ masterName: 'AV Content', sectionTitle: 'Ground and engineering' });
  header(s, '06 · GROUND SEGMENT AND ENGINEERING', 'Mission Control, security and quality', C.accent4);
  const cards = [
    ['Mission Control', C.accent4, 'Flight-surgeon role: crew status colours, every view audited'],
    ['Alerts', C.accent5, 'AlertGate confirmation rules; alerts state the delay to Earth; bell polls every 30 s'],
    ['History + reports', C.accent3, 'Chart.js trends, heat map, CSV export, ReportLab Downlink PDF'],
    ['Security', C.accent1, 'CSRF tokens, rate limits, HMAC device token, .env secrets'],
    ['Data layer', C.accent6, 'SQLAlchemy on SQLite (WAL), Alembic migrations, 30-day seed data'],
    ['Quality', C.accent2, '288 automated tests, firmware unit tests, verify script'],
  ];
  const w = 3.85;
  const h = 2.25;
  cards.forEach(([t, col, d], i) => {
    const x = 0.6 + (i % 3) * (w + 0.29);
    const y = 1.85 + Math.floor(i / 3) * (h + 0.35);
    card(s, x, y, w, h, `${t} card`);
    heading(s, x + 0.28, y + 0.22, w - 0.5, t, col, 22);
    s.addText(d, { x: x + 0.28, y: y + 0.82, w: w - 0.56, h: h - 1.0, fontSize: 18, color: C.background1, margin: 0, valign: 'top',
      isTextBox: true, objectName: `${t} text` });
  });
  s.addNotes('For the ground: Mission Control is a separate flight-surgeon role that sees status colours only, and every view is written to an audit log. Alerts pass through the AlertGate, and the escalation message states the communication delay to Earth. History uses Chart.js and exports CSV and a ReportLab one-page Downlink Report. Security: CSRF tokens, rate limiting, a constant-time device-token check, and secrets kept in .env. Data is SQLAlchemy on SQLite in WAL mode with Alembic migrations. Quality: 288 automated tests, firmware unit tests and a verify script that gates every build phase.');
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log('wrote', OUT);
})();
