#!/usr/bin/env node
/**
 * 带动画 PPTX：Playwright 逐页录屏（保留 CSS 入场动画）→ 嵌入每页视频
 *
 * 与 export_deck_pptx_lossless.mjs（静态截图）的区别：
 * - 无损版：等动画播完后截图 → 静态图片页，体积小、任意电脑可开
 * - 动画版：录制完整入场过程 → 每页一段视频，放映时与网站观感接近
 *
 * 依赖：npm install · npx playwright install chromium
 * 可选：系统安装 ffmpeg（用于 WebM→MP4，PowerPoint 兼容性更好）
 *
 * 用法：node scripts/export_deck_pptx_animated.mjs
 */

import { chromium } from 'playwright';
import pptxgen from 'pptxgenjs';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath, pathToFileURL } from 'url';
import { spawnSync } from 'child_process';
import { DECK_SLIDE_FILES } from '../shared/deck-manifest.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const SLIDES_DIR = path.join(ROOT, 'slides');
const OUT_DIR = path.join(ROOT, 'output');
const TMP_DIR = path.join(OUT_DIR, '_video_tmp');
const OUT_FILE = path.join(OUT_DIR, 'NA-自动配置工具-介绍-动画版.pptx');

const W = 1920;
const H = 1080;
/** 字体加载后再录动画（motion.css 最长约 d12×0.09+0.82≈1.9s，管线绘制 1.6s） */
const FONT_WAIT_MS = 1800;
const RECORD_MS = 4200;

function hasFfmpeg() {
  const r = spawnSync('ffmpeg', ['-version'], { stdio: 'ignore' });
  return r.status === 0;
}

function webmToMp4(inPath, outPath) {
  const r = spawnSync(
    'ffmpeg',
    ['-y', '-i', inPath, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', outPath],
    { stdio: 'inherit' }
  );
  return r.status === 0;
}

async function recordSlide(browser, file, index, useFfmpeg) {
  await fs.mkdir(TMP_DIR, { recursive: true });
  const videoDir = path.join(TMP_DIR, `slide_${String(index + 1).padStart(2, '0')}`);
  await fs.mkdir(videoDir, { recursive: true });

  const ctx = await browser.newContext({
    viewport: { width: W, height: H },
    deviceScaleFactor: 1,
    recordVideo: { dir: videoDir, size: { width: W, height: H } },
  });

  const page = await ctx.newPage();
  const url = pathToFileURL(path.join(SLIDES_DIR, file)).href + '?motion=full';

  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 }).catch(() =>
    page.goto(url, { waitUntil: 'load' })
  );
  await page.waitForTimeout(FONT_WAIT_MS);
  // 不调用 __deckFreezeReveals，保留完整 CSS 动画过程
  await page.waitForTimeout(RECORD_MS);

  const video = page.video();
  await page.close();
  await ctx.close();

  let webmPath = video ? await video.path() : null;
  if (!webmPath) throw new Error(`录制失败: ${file}`);

  const base = path.join(TMP_DIR, `${String(index + 1).padStart(2, '0')}_${path.basename(file, '.html')}`);
  const webmOut = `${base}.webm`;
  await fs.copyFile(webmPath, webmOut).catch(() => {});

  if (useFfmpeg) {
    const mp4Out = `${base}.mp4`;
    if (webmToMp4(webmPath, mp4Out)) return mp4Out;
    console.warn(`  ⚠ ffmpeg 转码失败，使用 WebM: ${file}`);
  }
  return webmOut;
}

async function main() {
  await fs.mkdir(OUT_DIR, { recursive: true });
  await fs.rm(TMP_DIR, { recursive: true, force: true }).catch(() => {});

  const files = DECK_SLIDE_FILES;
  if (!files.length) {
    console.error('slides/ 下没有 HTML 文件');
    process.exit(1);
  }

  const useFfmpeg = hasFfmpeg();
  console.log(`录制 ${files.length} 页动画 → ${OUT_FILE}`);
  if (!useFfmpeg) {
    console.log('提示: 未检测到 ffmpeg，将嵌入 WebM（部分 Office 版本可能无法播放）');
    console.log('      安装 ffmpeg 后重新导出可生成 MP4 版，兼容性更好\n');
  }

  const browser = await chromium.launch();
  const videos = [];

  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    console.log(`  [${i + 1}/${files.length}] 录制 ${f}…`);
    const vpath = await recordSlide(browser, f, i, useFfmpeg);
    videos.push(vpath);
  }
  await browser.close();

  const pres = new pptxgen();
  pres.layout = 'LAYOUT_WIDE';
  pres.author = 'NA Auto Configuration';
  pres.title = 'NA 自动配置工具 · 产品介绍（动画版）';

  for (const vpath of videos) {
    const slide = pres.addSlide();
    slide.addMedia({
      type: 'video',
      path: vpath,
      x: 0,
      y: 0,
      w: '100%',
      h: '100%',
    });
  }

  await pres.writeFile({ fileName: OUT_FILE });

  const stat = await fs.stat(OUT_FILE);
  console.log(`\n✓ 已生成 ${OUT_FILE}`);
  console.log(`  ${(stat.size / 1024 / 1024).toFixed(2)} MB · ${files.length} 页 · 每页含入场动画视频`);
  console.log('\n放映提示: PowerPoint「从头放映」时视频会自动播放；若未自动播放，请在「放映选项」中勾选自动播放媒体。');
  console.log('最佳动画体验仍推荐: docs/presentation/index.html → 开始演示（原生 CSS + 翻页）');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
