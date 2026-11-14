// BUILD-TIME ONLY. Produces committed files under app/static. End users never run this.
//
//   cd scripts/vendor_build && npm install && node build.mjs <task>
//
// Tasks: three | icons | textures | models | all
// Inputs that are downloaded (NASA ISS model, Earth maps, the humanoid) are fetched by
// `python scripts/fetch_build_sources.py` into build_sources/ (git-ignored) first.

import { mkdirSync, readFileSync, writeFileSync, existsSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..', '..');
const vendor = join(root, 'app', 'static', 'vendor');
const sources = join(root, 'build_sources');

const ICONS = `layout-grid heart bone mic stethoscope history log-out menu bell settings chevron-down check circle info x
plus droplet moon brain activity arrow-right arrow-left triangle-alert octagon-alert circle-check circle-dot globe orbit
satellite play pause square refresh-cw download user users shield thermometer wind gauge footprints dumbbell radio wifi
wifi-off bluetooth keyboard send volume-2 volume-x sparkles sun rocket timer hand camera camera-off file-text flame award
trophy trash-2 lock eye-off waves heart-pulse audio-lines mic-off calendar chart-line clipboard-list external-link
rotate-3d zap cpu list-checks loader-circle circle-help minus hourglass scan-face phone message-circle pencil`.split(/\s+/);

function kb(path) {
  return `${(statSync(path).size / 1024).toFixed(0)} KB`;
}

async function buildThree() {
  const { build } = await import('esbuild');
  const entry = join(here, 'three-entry.js');
  writeFileSync(entry, [
    "export * from 'three';",
    "export { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';",
    "export { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';",
    "export { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';",
    "export * as SkeletonUtils from 'three/examples/jsm/utils/SkeletonUtils.js';",
    '',
  ].join('\n'));
  const out = join(vendor, 'three', 'three.bundle.min.js');
  mkdirSync(dirname(out), { recursive: true });
  await build({
    entryPoints: [entry], bundle: true, minify: true, format: 'esm', target: 'es2020', outfile: out,
    legalComments: 'eof', logLevel: 'warning',
  });
  console.log(`three.bundle.min.js  ${kb(out)}`);
}

function buildIcons() {
  const dir = join(here, 'node_modules', 'lucide-static', 'icons');
  const symbols = ICONS.map((name) => {
    const svg = readFileSync(join(dir, `${name}.svg`), 'utf8');
    const inner = svg.replace(/^[\s\S]*?<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '').trim();
    return `<symbol id="${name}" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${inner.replace(/\s+/g, ' ')}</g></symbol>`;
  });
  const sprite = [
    '<svg xmlns="http://www.w3.org/2000/svg">',
    '<!-- Lucide icons (ISC licence, see LICENSE). Built by scripts/vendor_build/build.mjs -->',
    ...symbols,
    '</svg>',
    '',
  ].join('\n');
  const out = join(vendor, 'lucide', 'sprite.svg');
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, sprite);
  console.log(`lucide sprite        ${ICONS.length} icons, ${kb(out)}`);
}

async function buildTextures() {
  const sharp = (await import('sharp')).default;
  const out = join(root, 'app', 'static', 'textures');
  mkdirSync(out, { recursive: true });
  const jobs = [
    ['earth_day', 'earth-day.jpg'],
    ['earth_night', 'earth-night.jpg'],
    ['earth_clouds', 'earth-clouds.png'],
    ['earth_specular', 'earth-specular.jpg'],
  ];
  for (const [name, file] of jobs) {
    const input = join(sources, 'earth', file);
    if (!existsSync(input)) {
      console.log(`skip ${name}: ${input} missing`);
      continue;
    }
    for (const [tier, width] of [['2k', 2048], ['4k', 4096]]) {
      const target = join(out, `${name}_${tier}.webp`);
      let image = sharp(input).resize({ width, height: width / 2, fit: 'fill' });
      if (name === 'earth_clouds' || name === 'earth_specular') image = image.greyscale();
      await image.webp({ quality: name === 'earth_day' ? 82 : 76 }).toFile(target);
      console.log(`${name}_${tier}.webp  ${kb(target)}`);
    }
  }
  const stars = join(out, 'stars.webp');
  const size = 2048;
  const pixels = Buffer.alloc(size * (size / 2) * 3);
  let seed = 7;
  const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 2600; i += 1) {
    const x = Math.floor(rand() * size);
    const y = Math.floor(rand() * (size / 2));
    const v = Math.floor(90 + rand() ** 3 * 165);
    const o = (y * size + x) * 3;
    pixels[o] = v; pixels[o + 1] = v; pixels[o + 2] = Math.min(255, v + 10);
  }
  await sharp(pixels, { raw: { width: size, height: size / 2, channels: 3 } }).webp({ quality: 70 }).toFile(stars);
  console.log(`stars.webp           ${kb(stars)}`);
}

async function buildModels() {
  const { NodeIO } = await import('@gltf-transform/core');
  const { ALL_EXTENSIONS, EXTMeshoptCompression } = await import('@gltf-transform/extensions');
  const fn = await import('@gltf-transform/functions');
  const { MeshoptEncoder, MeshoptSimplifier } = await import('meshoptimizer');
  const sharp = (await import('sharp')).default;
  await MeshoptEncoder.ready;
  await MeshoptSimplifier.ready;
  const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
    'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptEncoder,
  });
  const out = join(root, 'app', 'static', 'models');
  mkdirSync(out, { recursive: true });

  // NASA ISS: drop only tiny greeble meshes, keep materials, resize textures, simplify lightly, meshopt.
  const issIn = join(sources, 'iss', 'iss.glb');
  if (existsSync(issIn)) {
    const doc = await io.read(issIn);
    const meshes = doc.getRoot().listMeshes();
    const greeble = /Details|Handrail|Handlebar|Lettering/i;
    const names = meshes.map((m) => m.getName());
    console.log(`ISS meshes: ${meshes.length}; sample names: ${names.slice(0, 25).join(', ')}`);
    let removed = 0;
    for (const node of doc.getRoot().listNodes()) {
      const mesh = node.getMesh();
      if (mesh && (greeble.test(mesh.getName()) || greeble.test(node.getName()))) {
        node.setMesh(null);
        removed += 1;
      }
    }
    console.log(`ISS: detached ${removed} greeble node(s)`);
    await doc.transform(
      fn.prune(), fn.dedup(), fn.weld(),
      fn.simplify({ simplifier: MeshoptSimplifier, ratio: 0.6, error: 0.0008 }),
      fn.textureCompress({ encoder: sharp, targetFormat: 'webp', resize: [1024, 1024] }),
      fn.quantize(), fn.prune(),
    );
    doc.createExtension(EXTMeshoptCompression).setRequired(true).setEncoderOptions({
      method: EXTMeshoptCompression.EncoderMethod.FILTER,
    });
    const target = join(out, 'iss.glb');
    await io.write(target, doc);
    let vertices = 0;
    for (const mesh of doc.getRoot().listMeshes()) {
      for (const prim of mesh.listPrimitives()) vertices += prim.getAttribute('POSITION')?.getCount() ?? 0;
    }
    console.log(`iss.glb ${kb(target)}, ${vertices} vertices`);
  } else {
    console.log(`skip ISS: ${issIn} missing`);
  }

  // Humanoid (three.js Xbot, Mixamo rig): meshopt-compress, keep the idle clip only.
  const botIn = join(sources, 'body', 'Xbot.glb');
  if (existsSync(botIn)) {
    const doc = await io.read(botIn);
    for (const anim of doc.getRoot().listAnimations()) {
      if (!/idle/i.test(anim.getName())) anim.dispose();
    }
    await doc.transform(fn.prune(), fn.dedup(), fn.quantize());
    doc.createExtension(EXTMeshoptCompression).setRequired(true);
    const target = join(out, 'astronaut.glb');
    await io.write(target, doc);
    console.log(`astronaut.glb ${kb(target)}, animations: ${doc.getRoot().listAnimations().map((a) => a.getName())}`);
  } else {
    console.log(`skip body: ${botIn} missing`);
  }
}

const task = process.argv[2] || 'all';
if (task === 'three' || task === 'all') await buildThree();
if (task === 'icons' || task === 'all') buildIcons();
if (task === 'textures' || task === 'all') await buildTextures();
if (task === 'models' || task === 'all') await buildModels();
