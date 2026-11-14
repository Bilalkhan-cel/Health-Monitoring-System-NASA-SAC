// Bone & Muscle: camera + MediaPipe Pose in the browser. Only keypoints are sent (≤ 15 per
// second); frames never leave the browser. HUD: reps, form, tempo, set timer, cues.

import { api, emitDataUpdated } from './api.js';
import { clear, h, prefersReducedMotion, statusPill, toast } from './dom.js';
import { SKELETON, meanConfidence, mediapipeToCoco } from './pose_adapters.js';

const root = document.querySelector('[data-body]');
const $ = (selector) => root.querySelector(selector);
const STATIC = document.querySelector('meta[name="static-root"]')?.content || '/static/';
const SEND_EVERY_MS = 70;   // ~14 keypoint frames per second
const BATCH_MS = 330;

const state = { landmarker: null, stream: null, raf: 0, exercise: null, sending: [], lastSend: 0, lastBatch: 0,
  reps: 0, setStarted: 0, voice: true, fps: 0, frames: 0, fpsWindow: performance.now(), active: false, busy: false,
  lastCueSpoken: '', plan: JSON.parse(root.dataset.plan || '[]') };

function show(step) {
  for (const section of root.querySelectorAll('[data-step]')) section.hidden = section.dataset.step !== step;
}

function speak(text) {
  if (!state.voice || !text || !('speechSynthesis' in window) || text === state.lastCueSpoken) return;
  state.lastCueSpoken = text;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}

async function loadLandmarker() {
  if (state.landmarker) return state.landmarker;
  const { FilesetResolver, PoseLandmarker } = await import(`${STATIC}vendor/mediapipe/vision_bundle.mjs`);
  const vision = await FilesetResolver.forVisionTasks(`${STATIC}vendor/mediapipe/wasm`);
  const options = (delegate) => ({ baseOptions: { modelAssetPath: `${STATIC}vendor/mediapipe/pose_landmarker_lite.task`,
    delegate }, runningMode: 'VIDEO', numPoses: 1, minPoseDetectionConfidence: 0.5, minTrackingConfidence: 0.5 });
  try {
    state.landmarker = await PoseLandmarker.createFromOptions(vision, options('GPU'));
  } catch {
    state.landmarker = await PoseLandmarker.createFromOptions(vision, options('CPU'));
  }
  return state.landmarker;
}

function drawSkeleton(keypoints) {
  const canvas = $('[data-overlay]');
  const video = $('[data-video]');
  const ctx = canvas.getContext('2d');
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!keypoints) return;
  const x = (p) => p[0] * canvas.width;
  const y = (p) => p[1] * canvas.height;
  ctx.lineWidth = Math.max(3, canvas.width / 220);
  ctx.strokeStyle = 'rgba(46,229,157,0.9)';
  ctx.shadowColor = 'rgba(46,229,157,0.8)';
  ctx.shadowBlur = 12;
  for (const [a, b] of SKELETON) {
    const p1 = keypoints[a];
    const p2 = keypoints[b];
    if (!p1 || !p2 || p1[2] < 0.4 || p2[2] < 0.4) continue;
    ctx.beginPath();
    ctx.moveTo(x(p1), y(p1));
    ctx.lineTo(x(p2), y(p2));
    ctx.stroke();
  }
  ctx.fillStyle = '#F2F4F7';
  for (const point of Object.values(keypoints)) {
    if (point[2] < 0.4) continue;
    ctx.beginPath();
    ctx.arc(x(point), y(point), Math.max(4, canvas.width / 160), 0, Math.PI * 2);
    ctx.fill();
  }
}

async function flush(now) {
  if (state.busy || !state.sending.length) return;
  state.busy = true;
  const frames = state.sending.splice(0, 30);
  try {
    const reply = await api('/musculoskeletal/keypoints', { method: 'POST', body: { frames } });
    renderHud(reply);
  } catch (error) {
    $('[data-cue]').textContent = error.message;
  } finally {
    state.busy = false;
    state.lastBatch = now;
  }
}

function loop() {
  state.raf = requestAnimationFrame(loop);
  const video = $('[data-video]');
  if (!state.active || !state.landmarker || video.readyState < 2) return;
  const now = performance.now();
  const result = state.landmarker.detectForVideo(video, now);
  const keypoints = mediapipeToCoco(result.landmarks?.[0]);
  drawSkeleton(keypoints);
  state.frames += 1;
  if (now - state.fpsWindow >= 1000) {
    state.fps = Math.round((state.frames * 1000) / (now - state.fpsWindow));
    state.frames = 0;
    state.fpsWindow = now;
    $('[data-fps]').textContent = `${state.fps} fps`;
  }
  const confidence = keypoints ? meanConfidence(keypoints) : 0;
  $('[data-confidence]').style.width = `${Math.round(confidence * 100)}%`;
  $('[data-confidence-label]').textContent = confidence > 0.6 ? 'Pose found' : 'Step back so your whole body is in view';
  if (keypoints && now - state.lastSend >= SEND_EVERY_MS) {
    state.lastSend = now;
    state.sending.push({ t: Number((now / 1000).toFixed(3)), kp: keypoints });
  }
  if (now - state.lastBatch >= BATCH_MS) flush(now);
  const elapsed = Math.round((Date.now() - state.setStarted) / 1000);
  $('[data-timer]').textContent = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;
}

function renderHud(reply) {
  const isRun = reply.exercise === 'run';
  $('[data-reps]').textContent = isRun ? (reply.steps ?? 0) : reply.reps;
  $('[data-reps-label]').textContent = isRun ? 'steps' : 'reps';
  $('[data-form]').textContent = reply.form ?? '–';
  $('[data-tempo]').textContent = isRun
    ? (reply.cadence ? `${Math.round(reply.cadence)} steps/min` : 'Cadence: keep going…')
    : (reply.reps > 0 && reply.duration_s ? `${(reply.duration_s / reply.reps).toFixed(1)} s per rep` : '–');
  if (reply.preview != null) $('[data-preview]').textContent = reply.preview;
  if (reply.cue) {
    $('[data-cue]').textContent = reply.cue;
    speak(reply.cue);
  }
  if (reply.rep_done && !prefersReducedMotion()) {
    const flash = $('[data-flash]');
    flash.classList.remove('is-on');
    void flash.offsetWidth;
    flash.classList.add('is-on');
  }
}

async function startCamera(exercise) {
  const message = $('[data-camera-message]');
  message.hidden = true;
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({ video: { width: 960, height: 540, facingMode: 'user' },
      audio: false });
  } catch (error) {
    message.hidden = false;
    message.textContent = error.name === 'NotAllowedError'
      ? 'Camera permission was refused. Allow the camera in the address bar and try again, or log a device session instead.'
      : 'No camera found. Log a device session instead.';
    return false;
  }
  const video = $('[data-video]');
  video.srcObject = state.stream;
  await video.play();
  try {
    $('[data-confidence-label]').textContent = 'Loading pose model…';
    await loadLandmarker();
  } catch {
    message.hidden = false;
    message.textContent = 'The pose model could not start in this browser. Log a device session instead.';
    stopCamera();
    return false;
  }
  state.exercise = exercise;
  state.active = true;
  state.setStarted = Date.now();
  if (!state.raf) loop();
  return true;
}

function stopCamera() {
  state.active = false;
  cancelAnimationFrame(state.raf);
  state.raf = 0;
  for (const track of state.stream?.getTracks() || []) track.stop();
  state.stream = null;
}

async function beginExercise(exercise) {
  try {
    await api('/musculoskeletal/start', { method: 'POST', body: { exercise } });
  } catch (error) {
    toast(error.message);
    return;
  }
  $('[data-set-title]').textContent = root.dataset[`name${exercise}`] || exercise;
  show('session');
  renderPlan(exercise);
  await startCamera(exercise);
}

function renderPlan(currentExercise) {
  const list = clear($('[data-plan]'));
  for (const item of state.plan) {
    const isNow = item.exercise === currentExercise;
    list.append(h('li', { class: `plan__item${isNow ? ' is-now' : ''}` },
      h('span', {}, item.label), h('span', { class: 'card__meta' }, isNow ? `Now · ${item.target}` : item.target)));
  }
}

async function nextSet() {
  const next = state.plan.find((item) => item.exercise !== state.exercise && item.exercise !== 'device_log')?.exercise;
  try {
    const reply = await api('/musculoskeletal/set', { method: 'POST', body: next ? { next } : {} });
    toast(reply.set ? 'Set saved.' : 'Nothing counted in that set yet.');
    if (next) {
      state.exercise = next;
      state.setStarted = Date.now();
      state.lastCueSpoken = '';
      $('[data-set-title]').textContent = root.dataset[`name${next}`] || next;
      renderPlan(next);
      renderHud({ exercise: next, reps: 0, steps: 0, form: null, preview: reply.preview });
    }
  } catch (error) {
    toast(error.message);
  }
}

async function endWorkout() {
  stopCamera();
  try {
    const reply = await api('/musculoskeletal/end', { method: 'POST', body: {} });
    renderResults(reply.results);
  } catch (error) {
    toast(error.message);
    show('overview');
  }
}

function renderResults(results) {
  show('results');
  if (!results.saved) {
    $('[data-result-title]').textContent = results.message;
    return;
  }
  $('[data-result-title]').textContent = results.before != null
    ? `Exercise load ${results.before} → ${results.loading_index}`
    : `Exercise load ${results.loading_index}`;
  clear($('[data-result-status]')).append(statusPill(results.status) || '');
  const sets = clear($('[data-result-sets]'));
  for (const item of results.sets) {
    const detail = item.exercise_type === 'device_log'
      ? `${Math.round(item.duration_s / 60)} min, effort ${item.effort_1_10}/10`
      : item.exercise_type === 'run'
        ? `${Math.round(item.duration_s / 60)} min${item.cadence_spm ? `, ${Math.round(item.cadence_spm)} steps/min` : ''}`
        : `${item.reps} reps${item.form_score != null ? `, form ${item.form_score}` : ''}`;
    sets.append(h('li', { class: 'row' }, h('span', { class: 'row__label' }, item.name), h('span', {}, detail)));
  }
  const tips = clear($('[data-result-tips]'));
  for (const tip of results.tips) tips.append(h('li', {}, tip));
  $('[data-result-previous]').textContent = results.previous
    ? `Last session (${results.previous.date}): exercise load ${results.previous.loading_index ?? '–'}.` : '';
  if (results.xp) toast(`Workout saved. +${results.xp} XP`);
  emitDataUpdated({ metric: 'loading_index' });
}

async function logDevice(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const error = $('[data-log-error]');
  try {
    await api('/musculoskeletal/start', { method: 'POST', body: {} });
    await api('/musculoskeletal/set', { method: 'POST', body: { exercise_type: 'device_log', device: data.get('device'),
      minutes: Number(data.get('minutes')), effort: Number(data.get('effort')) } });
    const reply = await api('/musculoskeletal/end', { method: 'POST', body: {} });
    error.hidden = true;
    renderResults(reply.results);
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  }
}

function setup() {
  for (const button of root.querySelectorAll('[data-exercise]')) {
    button.addEventListener('click', () => beginExercise(button.dataset.exercise));
  }
  $('[data-next]').addEventListener('click', nextSet);
  $('[data-end]').addEventListener('click', endWorkout);
  $('[data-retry]').addEventListener('click', () => startCamera(state.exercise));
  $('[data-log-form]').addEventListener('submit', logDevice);
  $('[data-voice]').addEventListener('change', (event) => { state.voice = event.target.checked; });
  $('[data-effort]').addEventListener('input', (event) => { $('[data-effort-value]').textContent = event.target.value; });
  for (const button of root.querySelectorAll('[data-back]')) button.addEventListener('click', () => {
    stopCamera();
    show('overview');
  });
  if (!navigator.mediaDevices?.getUserMedia) {
    for (const button of root.querySelectorAll('[data-exercise]')) button.disabled = true;
    $('[data-no-camera]').hidden = false;
  }
  window.addEventListener('beforeunload', stopCamera);
}

setup();
