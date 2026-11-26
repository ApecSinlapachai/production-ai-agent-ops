#!/usr/bin/env node
/**
 * Zero-dependency MP4 + GIF exporter for docs/assets/demo_animation.html
 * Uses local Chrome (CDP over WebSocket) + FFmpeg.
 *
 * Usage:
 *   node scripts/render_motion_demo.mjs
 *   node scripts/render_motion_demo.mjs --fps 30 --duration 22 --qa-dir /path/to/qa
 */
import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const getArg = (name, fallback) => {
  const idx = args.indexOf(`--${name}`);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : fallback;
};

const FPS = Number(getArg('fps', '30'));
const DURATION = Number(getArg('duration', '22'));
const QA_DIR = getArg('qa-dir', '');
const TOTAL_FRAMES = Math.round(FPS * DURATION);
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const HTML_PATH = path.join(REPO_ROOT, 'docs', 'assets', 'demo_animation.html');
const OUT_MP4 = path.join(REPO_ROOT, 'docs', 'assets', 'demo-motion.mp4');
const OUT_GIF = path.join(REPO_ROOT, 'docs', 'assets', 'demo-60s.gif');

const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
];
const CHROME = CHROME_CANDIDATES.find((p) => fs.existsSync(p));
if (!CHROME) {
  console.error('Chrome/Edge not found.');
  process.exit(1);
}

const framesDir = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-ops-motion-frames-'));
const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-ops-motion-chrome-'));
const port = 9222 + Math.floor(Math.random() * 500);

console.log(`Rendering ${TOTAL_FRAMES} frames (${DURATION}s @ ${FPS}fps) from ${HTML_PATH}...`);

const chromeProc = spawn(
  CHROME,
  [
    '--headless=new',
    '--disable-gpu',
    '--no-sandbox',
    '--hide-scrollbars',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--window-size=1920,1080',
    'about:blank',
  ],
  { stdio: 'ignore' }
);

async function waitForWsUrl() {
  for (let i = 0; i < 40; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/list`);
      const targets = await res.json();
      const page = targets.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error('Timed out waiting for Chrome DevTools Protocol.');
}

function encodeGif(palettePath, gifFps, maxColors) {
  const filter = `fps=${gifFps},scale=1280:-1:flags=lanczos`;
  execFileSync(
    'ffmpeg',
    ['-y', '-i', OUT_MP4, '-vf', `${filter},palettegen=max_colors=${maxColors}:stats_mode=diff`, palettePath],
    { stdio: 'inherit' }
  );
  execFileSync(
    'ffmpeg',
    [
      '-y',
      '-i', OUT_MP4,
      '-i', palettePath,
      '-lavfi', `${filter} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle`,
      OUT_GIF,
    ],
    { stdio: 'inherit' }
  );
}

async function run() {
  const wsUrl = await waitForWsUrl();
  const ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true });
    ws.addEventListener('error', reject, { once: true });
  });

  let nextId = 1;
  const pending = new Map();
  ws.addEventListener('message', (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message));
      else resolve(msg.result);
    }
  });

  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });

  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1920,
    height: 1080,
    deviceScaleFactor: 1,
    mobile: false,
  });

  const targetUrl = `${pathToFileURL(HTML_PATH).href}?export=1&t=0`;
  await send('Page.navigate', { url: targetUrl });
  await new Promise((r) => setTimeout(r, 1400));

  for (let i = 0; i < TOTAL_FRAMES; i++) {
    const t = i / FPS;
    await send('Runtime.evaluate', { expression: `window.seekTo(${t.toFixed(4)})` });
    const { data } = await send('Page.captureScreenshot', { format: 'png' });
    const framePath = path.join(framesDir, `frame_${String(i).padStart(5, '0')}.png`);
    fs.writeFileSync(framePath, Buffer.from(data, 'base64'));
    if ((i + 1) % 60 === 0 || i === TOTAL_FRAMES - 1) {
      process.stdout.write(`\rCaptured ${i + 1}/${TOTAL_FRAMES} frames`);
    }
  }

  // Optional Visual QA keyframes saved directly from the rendered frame buffer
  if (QA_DIR) {
    fs.mkdirSync(QA_DIR, { recursive: true });
    const qaTimes = [
      { name: 'qa_01_pdpa_redaction.png', sec: 5.0 },
      { name: 'qa_02_hitl_gate.png', sec: 8.0 },
      { name: 'qa_03_dlq_replay.png', sec: 12.2 },
      { name: 'qa_04_benchmark_verified.png', sec: 18.0 },
    ];
    for (const item of qaTimes) {
      const idx = Math.min(TOTAL_FRAMES - 1, Math.round(item.sec * FPS));
      const src = path.join(framesDir, `frame_${String(idx).padStart(5, '0')}.png`);
      if (fs.existsSync(src)) {
        fs.copyFileSync(src, path.join(QA_DIR, item.name));
      }
    }
  }

  console.log('\nEncoding MP4 via FFmpeg...');

  ws.close();
  chromeProc.kill();

  execFileSync(
    'ffmpeg',
    [
      '-y',
      '-framerate', String(FPS),
      '-i', path.join(framesDir, 'frame_%05d.png'),
      '-c:v', 'libx264',
      '-pix_fmt', 'yuv420p',
      '-crf', '18',
      '-movflags', '+faststart',
      OUT_MP4,
    ],
    { stdio: 'inherit' }
  );

  console.log('Encoding GitHub README GIF (1280x720, <= 8MB)...');
  const palettePath = path.join(framesDir, 'palette.png');
  encodeGif(palettePath, 15, 256);

  let gifBytes = fs.statSync(OUT_GIF).size;
  if (gifBytes > 8 * 1024 * 1024) {
    console.log(`GIF size ${(gifBytes / 1024 / 1024).toFixed(2)} MB > 8.00 MB; re-encoding with 12fps & 192 colors...`);
    encodeGif(palettePath, 12, 192);
    gifBytes = fs.statSync(OUT_GIF).size;
  }
  if (gifBytes > 8 * 1024 * 1024) {
    console.log(`GIF size ${(gifBytes / 1024 / 1024).toFixed(2)} MB > 8.00 MB; re-encoding with 10fps & 128 colors...`);
    encodeGif(palettePath, 10, 128);
    gifBytes = fs.statSync(OUT_GIF).size;
  }

  fs.rmSync(framesDir, { recursive: true, force: true });
  fs.rmSync(profileDir, { recursive: true, force: true });

  const mp4Mb = (fs.statSync(OUT_MP4).size / 1024 / 1024).toFixed(2);
  const gifMb = (fs.statSync(OUT_GIF).size / 1024 / 1024).toFixed(2);
  console.log(`\nDone!\n- MP4: ${OUT_MP4} (${mp4Mb} MB)\n- GIF: ${OUT_GIF} (${gifMb} MB)`);
}

run().catch((err) => {
  chromeProc.kill();
  console.error(err);
  process.exit(1);
});
