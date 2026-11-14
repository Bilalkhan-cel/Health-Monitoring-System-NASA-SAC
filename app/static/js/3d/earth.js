// Earth + NASA ISS scene (Section 6.1), used by the landing hero and the login page.
// Day/night blend by the sun direction with a soft terminator, ocean glint, drifting lit
// clouds, Fresnel haze and a back-side atmosphere shell. Quality tiers pick 2K/4K maps,
// clouds and the pixel ratio; a 1-second FPS probe steps down when the machine is slow.

import * as THREE from '../../vendor/three/three.bundle.min.js';
import { initialTier, forcedTier, probeFps, tierAfterProbe } from './quality.js';

const SUN = new THREE.Vector3(-1.0, 0.35, 0.55).normalize();

const EARTH_VERTEX = `
  varying vec2 vUv;
  varying vec3 vNormalW;
  varying vec3 vViewDir;
  void main() {
    vUv = uv;
    vec4 world = modelMatrix * vec4(position, 1.0);
    vNormalW = normalize(mat3(modelMatrix) * normal);
    vViewDir = normalize(cameraPosition - world.xyz);
    gl_Position = projectionMatrix * viewMatrix * world;
  }`;

const EARTH_FRAGMENT = `
  uniform sampler2D dayMap;
  uniform sampler2D nightMap;
  uniform sampler2D specMap;
  uniform sampler2D cloudMap;
  uniform vec3 sunDir;
  uniform float cloudShift;
  uniform float useClouds;
  varying vec2 vUv;
  varying vec3 vNormalW;
  varying vec3 vViewDir;
  void main() {
    vec3 n = normalize(vNormalW);
    float light = dot(n, sunDir);
    float dayAmount = smoothstep(-0.18, 0.28, light);
    vec3 day = texture2D(dayMap, vUv).rgb;
    vec3 night = texture2D(nightMap, vUv).rgb * vec3(1.0, 0.85, 0.62) * 1.6;
    float clouds = useClouds * texture2D(cloudMap, vec2(vUv.x + cloudShift, vUv.y)).r;
    vec3 color = mix(night * (1.0 - clouds), day * (0.25 + 0.95 * max(light, 0.0)), dayAmount);
    color = mix(color, vec3(1.0) * (0.12 + 0.95 * max(light, 0.0)), clouds * 0.85 * dayAmount);
    float ocean = texture2D(specMap, vUv).r;
    vec3 halfDir = normalize(sunDir + vViewDir);
    float glint = pow(max(dot(n, halfDir), 0.0), 90.0) * ocean * (1.0 - clouds) * dayAmount;
    color += vec3(1.0, 0.92, 0.78) * glint * 0.9;
    float fresnel = pow(1.0 - max(dot(n, vViewDir), 0.0), 3.0);
    color += vec3(0.30, 0.62, 1.0) * fresnel * (0.25 + 0.75 * dayAmount) * 0.9;
    gl_FragColor = vec4(color, 1.0);
    #include <colorspace_fragment>
  }`;

const ATMOSPHERE_FRAGMENT = `
  uniform vec3 sunDir;
  varying vec3 vNormalW;
  varying vec3 vViewDir;
  void main() {
    vec3 n = normalize(vNormalW);
    // Back faces: d is about -0.35 just outside the limb and 0 at the shell's own edge.
    float d = -dot(n, vViewDir);
    float glow = smoothstep(0.0, 0.32, d) * (1.0 - smoothstep(0.32, 0.62, d));
    float lit = smoothstep(-0.35, 0.6, dot(n, sunDir));
    vec3 color = mix(vec3(0.25, 0.5, 1.0), vec3(0.6, 0.85, 1.0), lit) + vec3(1.0, 0.75, 0.5) * lit * 0.15;
    gl_FragColor = vec4(color, glow * (0.2 + 0.8 * lit));
  }`;

function texture(loader, url, colorSpace) {
  return new Promise((resolve) => {
    loader.load(url, (tex) => {
      tex.colorSpace = colorSpace;
      tex.anisotropy = 8;
      resolve(tex);
    }, undefined, () => resolve(null));
  });
}

export async function mountEarthScene(canvas, { variant = 'hero', staticRoot = '/static/', onProgress } = {}) {
  let tier = forcedTier() || initialTier();
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, tier.dprCap));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.setClearColor(0x000000, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 400);
  const loader = new THREE.TextureLoader();
  const tex = (name) => `${staticRoot}textures/${name}_${tier.textures}.webp`;
  const [day, night, spec, clouds, stars] = await Promise.all([
    texture(loader, tex('earth_day'), THREE.SRGBColorSpace),
    texture(loader, tex('earth_night'), THREE.SRGBColorSpace),
    texture(loader, tex('earth_specular'), THREE.NoColorSpace),
    tier.clouds ? texture(loader, tex('earth_clouds'), THREE.NoColorSpace) : Promise.resolve(null),
    texture(loader, `${staticRoot}textures/stars.webp`, THREE.SRGBColorSpace),
  ]);
  if (!day || !night) throw new Error('Earth textures missing');

  // Stars
  if (stars) {
    const sky = new THREE.Mesh(new THREE.SphereGeometry(180, 32, 16),
      new THREE.MeshBasicMaterial({ map: stars, side: THREE.BackSide, color: 0x8a8f99 }));
    scene.add(sky);
  }

  // Earth
  const earthGroup = new THREE.Group();
  const uniforms = {
    dayMap: { value: day }, nightMap: { value: night }, specMap: { value: spec || day },
    cloudMap: { value: clouds || day }, sunDir: { value: SUN }, cloudShift: { value: 0 },
    useClouds: { value: clouds ? 1 : 0 },
  };
  const earth = new THREE.Mesh(new THREE.SphereGeometry(1, 192, 96),
    new THREE.ShaderMaterial({ uniforms, vertexShader: EARTH_VERTEX, fragmentShader: EARTH_FRAGMENT }));
  earth.rotation.y = -1.9;
  earthGroup.add(earth);
  const atmosphere = new THREE.Mesh(new THREE.SphereGeometry(1.07, 96, 48),
    new THREE.ShaderMaterial({ uniforms: { sunDir: { value: SUN } }, vertexShader: EARTH_VERTEX,
      fragmentShader: ATMOSPHERE_FRAGMENT, side: THREE.BackSide, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending }));
  earthGroup.add(atmosphere);
  earthGroup.rotation.z = 0.41;
  scene.add(earthGroup);

  // Lighting for the station
  scene.add(new THREE.AmbientLight(0x404a5a, 0.6));
  const sunLight = new THREE.DirectionalLight(0xffffff, 3.2);
  sunLight.position.copy(SUN).multiplyScalar(10);
  scene.add(sunLight);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new THREE.RoomEnvironment(), 0.04).texture;

  // Framing
  const layouts = {
    hero: { earth: [0, -1.82, 0], scale: 1.25, camera: [0, 0.05, 4.2], look: [0, -0.1, 0], stationX: -0.66, stationY: 0.97 },
    login: { earth: [0, -2.15, 0], scale: 1.7, camera: [0, 0.05, 4.4], look: [0, -0.25, 0], stationX: -0.44, stationY: 0.9 },
  };
  const layout = layouts[variant] || layouts.hero;
  earthGroup.position.set(...layout.earth);
  earthGroup.scale.setScalar(layout.scale);
  camera.position.set(...layout.camera);
  const look = new THREE.Vector3(...layout.look);
  camera.lookAt(look);

  // ISS (loaded after the Earth is on screen)
  const station = new THREE.Group();
  scene.add(station);
  let iss = null;
  const loadStation = async () => {
    const gltfLoader = new THREE.GLTFLoader();
    gltfLoader.setMeshoptDecoder(THREE.MeshoptDecoder);
    const gltf = await gltfLoader.loadAsync(`${staticRoot}models/iss.glb`, (event) => {
      if (event.total) onProgress?.(event.loaded / event.total);
    });
    iss = gltf.scene;
    const box = new THREE.Box3().setFromObject(iss);
    const size = box.getSize(new THREE.Vector3()).length() || 1;
    iss.scale.setScalar((variant === 'login' ? 0.62 : 0.8) / size);
    box.setFromObject(iss);
    iss.position.sub(box.getCenter(new THREE.Vector3()));
    iss.traverse((node) => {
      if (node.isMesh && node.material) {
        for (const material of [].concat(node.material)) {
          for (const key of ['map', 'emissiveMap', 'normalMap', 'roughnessMap', 'metalnessMap']) {
            if (material[key]) material[key].anisotropy = renderer.capabilities.getMaxAnisotropy();
          }
        }
      }
    });
    station.add(iss);
  };
  const stationReady = loadStation().catch(() => null);

  // Size, parallax, scroll progress
  const resize = () => {
    const width = canvas.clientWidth || window.innerWidth;
    const height = canvas.clientHeight || window.innerHeight;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  };
  window.addEventListener('resize', resize);
  resize();
  const mouse = { x: 0, y: 0, tx: 0, ty: 0 };
  const onMove = (event) => {
    mouse.tx = (event.clientX / window.innerWidth - 0.5) * 2;
    mouse.ty = (event.clientY / window.innerHeight - 0.5) * 2;
  };
  window.addEventListener('pointermove', onMove, { passive: true });
  let progress = 0;

  const clock = new THREE.Clock();
  let running = true;
  let raf = 0;
  const api = { tier: tier.name, fps: 0, ready: stationReady };
  stationReady.then(() => { document.documentElement.dataset.sceneReady = '1'; });
  let frames = 0;
  let windowStart = performance.now();
  const loop = () => {
    if (!running) return;
    raf = requestAnimationFrame(loop);
    if (document.hidden) return;
    const t = clock.getElapsedTime();
    earth.rotation.y = -1.9 + t * 0.01;
    uniforms.cloudShift.value = t * 0.0015;
    mouse.x += (mouse.tx - mouse.x) * 0.04;
    mouse.y += (mouse.ty - mouse.y) * 0.04;
    // The station drifts along an inclined orbit over the limb (±18°), never behind the planet.
    const angle = THREE.MathUtils.degToRad(18) * Math.sin(t * 0.05);
    const radius = 1.42 * layout.scale;
    const center = earthGroup.position;
    // Pull the station in on narrow screens so it never leaves the frame.
    const reach = Math.min(1, camera.aspect / 1.78);
    station.position.set(center.x + (radius * layout.stationX + Math.sin(angle) * radius * 0.14) * reach,
      center.y + radius * layout.stationY + Math.cos(angle) * 0.04, center.z + 0.9);
    station.scale.setScalar(0.55 + 0.45 * reach);
    station.rotation.set(0.35, t * 0.04 + 0.6, -0.25 + angle * 0.4);
    const dolly = variant === 'hero' ? progress : 0;
    camera.position.set(layout.camera[0] + mouse.x * 0.12 + dolly * 0.25,
      layout.camera[1] - mouse.y * 0.06 + dolly * 0.55, layout.camera[2] - dolly * 1.9);
    camera.lookAt(look.x + dolly * 0.2, look.y + dolly * 0.9, look.z);
    renderer.render(scene, camera);
    frames += 1;
    const now = performance.now();
    if (now - windowStart >= 1000) {
      api.fps = Math.round((frames * 1000) / (now - windowStart));
      frames = 0;
      windowStart = now;
    }
  };
  loop();

  if (!forcedTier()) {
    probeFps(1000).then((fps) => {
      const next = tierAfterProbe(tier, fps);
      if (next !== tier) {
        tier = next;
        api.tier = tier.name;
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, tier.dprCap));
        if (!tier.clouds) uniforms.useClouds.value = 0;
        resize();
      }
    });
  }

  return Object.assign(api, {
    setProgress(value) { progress = Math.max(0, Math.min(1, value)); },
    destroy() {
      running = false;
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onMove);
      renderer.dispose();
    },
  });
}
