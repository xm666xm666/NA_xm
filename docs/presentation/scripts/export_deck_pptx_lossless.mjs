#!/usr/bin/env node
/**
 * 静态 PPTX（无动画）：Playwright 逐页渲染 1920×1080 PNG → 全幅嵌入 PowerPoint
 * 使用 ?motion=off 立刻定格最终画面，不录制、不播放入场动画。
 *
 * 用法：node scripts/export_deck_pptx_lossless.mjs
 */

import { chromium } from 'playwright';
import pptxgen from 'pptxgenjs';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath, pathToFileURL } from 'url';
import { DECK_SLIDE_FILES } from '../shared/deck-manifest.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const SLIDES_DIR = path.join(ROOT, 'slides');
const OUT_DIR = path.join(ROOT, 'output');
const OUT_FILE = path.join(OUT_DIR, 'NA-自动配置工具-介绍.pptx');

const W = 1920;
const H = 1080;
const FONT_WAIT_MS = 2000;

async function main() {
  await fs.mkdir(OUT_DIR, { recursive: true });

  const files = DECK_SLIDE_FILES;

  if (!files.length) {
    console.error('slides/ 下没有 HTML 文件');
    process.exit(1);
  }

  console.log(`静态导出（无动画） ${files.length} 页 → ${OUT_FILE}`);

  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: W, height: H },
    deviceScaleFactor: 2,
  });

  const images = [];

  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    const page = await ctx.newPage();
    const url = pathToFileURL(path.join(SLIDES_DIR, f)).href + '?motion=off';

    await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 }).catch(() =>
      page.goto(url, { waitUntil: 'load' })
    );
    await page.waitForTimeout(FONT_WAIT_MS);
    await page.evaluate(() => {
      document.body.classList.add('motion-lite');
      document.body.classList.remove('motion-full');
      if (typeof window.__deckFreezeReveals === 'function') window.__deckFreezeReveals();
    });

    const pngPath = path.join(OUT_DIR, `_tmp_${String(i + 1).padStart(2, '0')}.png`);
    await page.screenshot({
      path: pngPath,
      type: 'png',
      clip: { x: 0, y: 0, width: W, height: H },
    });
    images.push(pngPath);
    await page.close();
    console.log(`  [${i + 1}/${files.length}] ${f}`);
  }

  await browser.close();

  const pres = new pptxgen();
  pres.layout = 'LAYOUT_WIDE';
  pres.author = 'NA Auto Configuration';
  pres.title = 'NA 自动配置工具 · 产品介绍';

  for (let i = 0; i < images.length; i++) {
    const slide = pres.addSlide();
    slide.addImage({
      path: images[i],
      x: 0,
      y: 0,
      w: '100%',
      h: '100%',
    });
  }

  await pres.writeFile({ fileName: OUT_FILE });

  for (const p of images) {
    await fs.unlink(p).catch(() => {});
  }

  const stat = await fs.stat(OUT_FILE);
  console.log(`\n✓ 已生成 ${OUT_FILE}`);
  console.log(`  ${(stat.size / 1024 / 1024).toFixed(2)} MB · ${files.length} 页 · 静态无动画`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
