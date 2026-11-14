// 3D digital twin (Section 9.5): a rigged humanoid drawn as a hologram, with a beating
// heart on the chest bone, a wireframe brain on the head bone and three hotspots that
// follow the idle animation. Exposes select(), setStatus() and setHeartRate().

import * as THREE from '../../vendor/three/three.bundle.min.js';

const GLOW = new THREE.Color('#7CF3FF');
const STATUS_COLORS = { good: '#2EE59D', okay: '#3B9EFF', watch: '#FFC53D', alert: '#FF4D6D' };
const TARGET_HEIGHT = 1.85;
const BONE_PATTERNS = {
  head: [/head$/i, /head/i],
  chest: [/spine2$/i, /spine_?02/i, /chest/i, /spine1$/i, /spine/i],
  leftKnee: [/leftleg$/i, /left_?knee/i, /l_?calf/i, /leg_?l/i],
  hips: [/hips$/i, /pelvis/i],
};
const HOTSPOTS = [
  { system: 'mind', bone: 'head', offset: [0, 0.11, 0.02], label: 'Mind' },
  { system: 'heart', bone: 'chest', offset: [0.05, 0.03, 0.1], label: 'Heart' },
  { system: 'bones', bone: 'leftKnee', offset: [0, 0.02, 0.06], label: 'Bones' },
];

function findBone(root, patterns) {
  const bones = [];
  root.traverse((node) => { if (node.isBone) bones.push(node); });
  for (const pattern of patterns) {
    const bone = bones.find((candidate) => pattern.test(candidate.name));
    if (bone) return bone;
  }
  return null;
}

function hologramMaterial() {
  const material = new THREE.MeshStandardMaterial({
    color: GLOW, emissive: GLOW, emissiveIntensity: 0.15, transparent: true, opacity: 0.06,
    roughness: 0.4, metalness: 0, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uGlow = { value: GLOW };
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform vec3 uGlow;')
      .replace('#include <dithering_fragment>', [
        '#include <dithering_fragment>',
        'float rim = pow(1.0 - abs(dot(normalize(normal), normalize(vViewPosition))), 2.4);',
        'gl_FragColor.rgb += uGlow * rim * 0.9;',
        'gl_FragColor.a = clamp(opacity + rim * 0.55, 0.0, 1.0);',
      ].join('\n'));
  };
  return material;
}

function heartGeometry() {
  const shape = new THREE.Shape();
  shape.moveTo(0, -0.5);
  shape.bezierCurveTo(0.1, -0.35, 0.55, -0.1, 0.5, 0.2);
  shape.bezierCurveTo(0.46, 0.5, 0.12, 0.55, 0, 0.3);
  shape.bezierCurveTo(-0.12, 0.55, -0.46, 0.5, -0.5, 0.2);
  shape.bezierCurveTo(-0.55, -0.1, -0.1, -0.35, 0, -0.5);
  const geometry = new THREE.ExtrudeGeometry(shape, { depth: 0.35, bevelEnabled: true, bevelThickness: 0.12,
    bevelSize: 0.08, bevelSegments: 4, curveSegments: 18 });
  geometry.center();
  geometry.scale(0.11, 0.11, 0.11);
  return geometry;
}

function discTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext('2d');
  const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  gradient.addColorStop(0, 'rgba(124,243,255,0.55)');
  gradient.addColorStop(0.5, 'rgba(124,243,255,0.12)');
  gradient.addColorStop(1, 'rgba(124,243,255,0)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(canvas);
}

function scanTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 4;
  canvas.height = 64;
  const ctx = canvas.getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 64);
  gradient.addColorStop(0, 'rgba(124,243,255,0)');
  gradient.addColorStop(0.5, 'rgba(124,243,255,0.9)');
  gradient.addColorStop(1, 'rgba(124,243,255,0)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 4, 64);
  return new THREE.CanvasTexture(canvas);
}

export async function mountBody(container, { onSelect, modelUrl, reducedMotion = false, dprCap = 1.75,
  showTags = true } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, dprCap));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const canvas = renderer.domElement;
  canvas.setAttribute('aria-hidden', 'true');

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.05, 40);
  camera.position.set(0, 1.0, 4.3);
  camera.lookAt(0, 0.93, 0);
  scene.add(new THREE.HemisphereLight(0xbfefff, 0x05080c, 1.2));
  const key = new THREE.DirectionalLight(0xffffff, 1.4);
  key.position.set(-2, 3, 3);
  scene.add(key);

  const loader = new THREE.GLTFLoader();
  loader.setMeshoptDecoder(THREE.MeshoptDecoder);
  const gltf = await loader.loadAsync(modelUrl);
  const model = gltf.scene;
  const pivot = new THREE.Group();
  pivot.add(model);
  scene.add(pivot);

  // Measure height from bone world positions (skinned-mesh bounds are unreliable).
  model.updateMatrixWorld(true);
  const found = Object.fromEntries(Object.entries(BONE_PATTERNS).map(([name, patterns]) => [name,
    findBone(model, patterns)]));
  const head = found.head ? new THREE.Vector3().setFromMatrixPosition(found.head.matrixWorld) : null;
  let lowest = Infinity;
  model.traverse((node) => {
    if (node.isBone) lowest = Math.min(lowest, new THREE.Vector3().setFromMatrixPosition(node.matrixWorld).y);
  });
  const measured = head ? head.y - lowest + 0.12 : 1.8;
  model.scale.multiplyScalar(TARGET_HEIGHT / measured);
  model.updateMatrixWorld(true);
  let floor = Infinity;
  model.traverse((node) => {
    if (node.isBone) floor = Math.min(floor, new THREE.Vector3().setFromMatrixPosition(node.matrixWorld).y);
  });
  model.position.y -= floor - 0.02;

  // Hologram body + wireframe layer that shares the same skeleton.
  const skinned = [];
  model.traverse((node) => { if (node.isSkinnedMesh) skinned.push(node); });
  const holo = hologramMaterial();
  const wireMaterial = new THREE.MeshBasicMaterial({ color: GLOW, wireframe: true, transparent: true, opacity: 0.07,
    depthWrite: false, blending: THREE.AdditiveBlending });
  for (const mesh of skinned) {
    mesh.material = holo;
    mesh.frustumCulled = false;
    const wire = new THREE.SkinnedMesh(mesh.geometry, wireMaterial);
    wire.bind(mesh.skeleton, mesh.bindMatrix);
    wire.frustumCulled = false;
    mesh.parent.add(wire);
  }
  const skeleton = new THREE.SkeletonHelper(model);
  skeleton.material.color = GLOW;
  skeleton.material.transparent = true;
  skeleton.material.opacity = 0.5;
  skeleton.material.blending = THREE.AdditiveBlending;
  scene.add(skeleton);

  // Floor rings and a soft disc under the feet.
  const floorGroup = new THREE.Group();
  const disc = new THREE.Mesh(new THREE.CircleGeometry(0.9, 48),
    new THREE.MeshBasicMaterial({ map: discTexture(), transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending }));
  disc.rotation.x = -Math.PI / 2;
  floorGroup.add(disc);
  for (const [inner, opacity] of [[0.45, 0.5], [0.7, 0.28], [0.95, 0.15]]) {
    const ring = new THREE.Mesh(new THREE.RingGeometry(inner, inner + 0.008, 96),
      new THREE.MeshBasicMaterial({ color: GLOW, transparent: true, opacity, side: THREE.DoubleSide,
        depthWrite: false }));
    ring.rotation.x = -Math.PI / 2;
    floorGroup.add(ring);
  }
  floorGroup.position.y = 0.005;
  scene.add(floorGroup);

  // Scan band that sweeps up the body.
  const scan = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.06, 48, 1, true),
    new THREE.MeshBasicMaterial({ map: scanTexture(), transparent: true, opacity: 0, depthWrite: false,
      blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
  pivot.add(scan);

  // Organs on bones.
  const heartMaterial = new THREE.MeshStandardMaterial({ color: '#FF4D6D', emissive: '#FF4D6D',
    emissiveIntensity: 0.9, roughness: 0.35, transparent: true, opacity: 0.92 });
  const heart = new THREE.Mesh(heartGeometry(), heartMaterial);
  heart.rotation.z = Math.PI;
  if (found.chest) {
    found.chest.add(heart);
    heart.scale.setScalar(1 / model.scale.x);
    heart.position.set(0.04, 0.02, 0.07).multiplyScalar(1 / model.scale.x);
  }
  const brainMaterial = new THREE.MeshBasicMaterial({ color: '#3B9EFF', wireframe: true, transparent: true,
    opacity: 0.75 });
  const brain = new THREE.Mesh(new THREE.IcosahedronGeometry(0.07, 2), brainMaterial);
  brain.scale.set(1, 0.82, 1.15);
  if (found.head) {
    found.head.add(brain);
    brain.scale.multiplyScalar(1 / model.scale.x);
    brain.position.set(0, 0.1, 0.01).multiplyScalar(1 / model.scale.x);
  }

  // Hotspots: invisible hit spheres on bones + billboarded rings and halos.
  const hitTargets = [];
  const spots = {};
  for (const spot of HOTSPOTS) {
    const bone = found[spot.bone];
    if (!bone) continue;
    const anchor = new THREE.Object3D();
    anchor.position.set(...spot.offset).multiplyScalar(1 / model.scale.x);
    bone.add(anchor);
    const hit = new THREE.Mesh(new THREE.SphereGeometry(0.16, 12, 12), new THREE.MeshBasicMaterial({ visible: false }));
    hit.userData.system = spot.system;
    scene.add(hit);
    hitTargets.push(hit);
    const ringMaterial = new THREE.MeshBasicMaterial({ color: GLOW, transparent: true, opacity: 0.95,
      depthTest: false, side: THREE.DoubleSide });
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.055, 0.068, 48), ringMaterial);
    const haloMaterial = new THREE.MeshBasicMaterial({ color: GLOW, transparent: true, opacity: 0.18,
      depthTest: false, side: THREE.DoubleSide });
    const halo = new THREE.Mesh(new THREE.CircleGeometry(0.11, 40), haloMaterial);
    ring.renderOrder = 10;
    halo.renderOrder = 9;
    scene.add(ring, halo);
    let tag = null;
    if (showTags) {
      tag = document.createElement('span');
      tag.className = 'twin-tag';
      tag.setAttribute('aria-hidden', 'true');
      tag.textContent = spot.label;
      container.append(tag);
    }
    spots[spot.system] = { anchor, hit, ring, halo, ringMaterial, haloMaterial, tag, label: spot.label,
      hover: false, selected: false };
  }

  const mixer = new THREE.AnimationMixer(model);
  const clip = gltf.animations.find((item) => /idle/i.test(item.name)) || gltf.animations[0];
  if (clip && !reducedMotion) mixer.clipAction(clip).play();

  container.append(canvas);

  // Size
  const resize = () => {
    const width = container.clientWidth || 1;
    const height = container.clientHeight || 1;
    renderer.setSize(width, height, false);
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    camera.aspect = width / height;
    const fit = height / width > 1.25 ? 0.9 : 0;
    camera.position.z = 4.3 + fit;
    camera.updateProjectionMatrix();
  };
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(container);
  resize();

  // Drag to turn with momentum; tap a hotspot to select.
  const pointer = new THREE.Vector2();
  const raycaster = new THREE.Raycaster();
  let dragging = false;
  let moved = 0;
  let lastX = 0;
  let velocity = 0;
  let idleSince = performance.now();
  const pick = (event) => {
    const rect = canvas.getBoundingClientRect();
    pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(hitTargets)[0];
    return hit ? hit.object.userData.system : null;
  };
  canvas.addEventListener('pointerdown', (event) => {
    dragging = true;
    moved = 0;
    lastX = event.clientX;
    velocity = 0;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', (event) => {
    if (dragging) {
      const dx = event.clientX - lastX;
      lastX = event.clientX;
      moved += Math.abs(dx);
      velocity = dx * 0.008;
      pivot.rotation.y += velocity;
      idleSince = performance.now();
      return;
    }
    const system = pick(event);
    for (const [id, spot] of Object.entries(spots)) spot.hover = id === system;
    canvas.style.cursor = system ? 'pointer' : 'grab';
  });
  canvas.addEventListener('pointerup', (event) => {
    dragging = false;
    if (moved < 6) {
      const system = pick(event);
      if (system) onSelect?.(system);
    }
  });
  canvas.addEventListener('pointerleave', () => {
    for (const spot of Object.values(spots)) spot.hover = false;
  });

  // Render loop (paused when hidden or off screen).
  const clock = new THREE.Clock();
  const world = new THREE.Vector3();
  let bpm = null;
  let running = true;
  let visible = true;
  let frame = 0;
  let frames = 0;
  let fpsWindowStart = performance.now();
  const api = { kind: '3d', hint: 'Drag to turn · tap a glowing point', fps: 0,
    bones: Object.fromEntries(Object.entries(found).map(([k, v]) => [k, v ? v.name : null])) };

  const loop = () => {
    if (!running) return;
    frame = requestAnimationFrame(loop);
    if (!visible || document.hidden) return;
    const delta = Math.min(clock.getDelta(), 0.1);
    const t = clock.elapsedTime;
    mixer.update(delta);
    if (!dragging) {
      velocity *= 0.94;
      pivot.rotation.y += velocity;
      if (!reducedMotion && performance.now() - idleSince > 2500) pivot.rotation.y += delta * 0.18;
    }
    if (!reducedMotion) pivot.position.y = Math.sin(t * 0.7) * 0.025;

    const sweep = reducedMotion ? -1 : (t % 4.5) / 3;
    scan.position.y = Math.min(sweep, 1) * 1.95;
    scan.material.opacity = sweep >= 0 && sweep <= 1 ? Math.sin(sweep * Math.PI) * 0.5 : 0;

    const beat = bpm ? (t * bpm) / 60 : 0;
    const pulse = bpm ? 1 + 0.16 * Math.max(0, Math.sin(beat * Math.PI * 2)) ** 8 : 1;
    heart.scale.setScalar(pulse / model.scale.x);
    heartMaterial.emissiveIntensity = bpm ? 0.6 + (pulse - 1) * 4 : 0.45 + Math.sin(t * 1.2) * 0.1;
    brain.rotation.y = t * 0.25;

    const rect = canvas.getBoundingClientRect();
    for (const spot of Object.values(spots)) {
      spot.anchor.getWorldPosition(world);
      spot.hit.position.copy(world);
      spot.ring.position.copy(world);
      spot.halo.position.copy(world);
      spot.ring.quaternion.copy(camera.quaternion);
      spot.halo.quaternion.copy(camera.quaternion);
      const grow = spot.hover || spot.selected ? 1.35 : 1;
      spot.ring.scale.setScalar(grow);
      const wave = reducedMotion ? 1.2 : 1 + 0.45 * ((Math.sin(t * 2.4) + 1) / 2);
      spot.halo.scale.setScalar(wave * grow);
      spot.haloMaterial.opacity = 0.22 - (wave - 1) * 0.3;
      if (spot.tag) {
        const projected = world.clone().project(camera);
        const x = ((projected.x + 1) / 2) * rect.width;
        const y = ((-projected.y + 1) / 2) * rect.height;
        spot.tag.style.transform = `translate(${Math.round(x + 18)}px, ${Math.round(y - 12)}px)`;
        spot.tag.style.opacity = projected.z < 1 ? '1' : '0';
      }
    }
    renderer.render(scene, camera);
    frames += 1;
    const now = performance.now();
    if (now - fpsWindowStart >= 1000) {
      api.fps = Math.round((frames * 1000) / (now - fpsWindowStart));
      frames = 0;
      fpsWindowStart = now;
    }
  };
  const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; });
  io.observe(container);
  loop();

  Object.assign(api, {
    select(system) {
      for (const [id, spot] of Object.entries(spots)) spot.selected = id === system;
    },
    setStatus(systems) {
      for (const [id, spot] of Object.entries(spots)) {
        const info = systems[id] || {};
        const color = new THREE.Color(STATUS_COLORS[info.key] || '#7CF3FF');
        spot.ringMaterial.color = color;
        spot.haloMaterial.color = color;
        if (spot.tag) {
          spot.tag.textContent = `${spot.label}${info.score != null ? ` ${info.score}` : ''}`;
          spot.tag.dataset.status = info.key || '';
        }
        if (id === 'heart') heartMaterial.color = heartMaterial.emissive = color.clone();
        if (id === 'mind') brainMaterial.color = color.clone();
      }
    },
    setHeartRate(value) {
      bpm = value && value > 20 && value < 240 ? value : null;
    },
    destroy() {
      running = false;
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      io.disconnect();
      renderer.dispose();
      canvas.remove();
      for (const spot of Object.values(spots)) spot.tag?.remove();
    },
  });
  return api;
}
