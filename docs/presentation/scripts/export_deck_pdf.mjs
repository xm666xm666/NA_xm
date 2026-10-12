#!/usr/bin/env node
/** 矢量 PDF 导出（文字可复制） */
import { chromium } from 'playwright';
import { PDFDocument } from 'pdf-lib';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath, pathToFileURL } from 'url';
import { DECK_SLIDE_FILES } from '../shared/deck-manifest.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const SLIDES_DIR = path.join(ROOT, 'slides');
const OUT_DIR = path.join(ROOT, 'output');
const OUT_FILE = path.join(OUT_DIR, 'NA-自动配置工具-介绍.pdf');
const W = 1920;
const H = 1080;

async function main() {
  await fs.mkdir(OUT_DIR, { recursive: true });
  const files = DECK_SLIDE_FILES;
  console.log(`导出 PDF ${files.length} 页 → ${OUT_FILE}`);

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: W, height: H } });
  const pageBuffers = [];

  for (const f of files) {
    const page = await ctx.newPage();
    const url = pathToFileURL(path.join(SLIDES_DIR, f)).href + '?motion=full';
    await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 }).catch(() =>
      page.goto(url, { waitUntil: 'load' })
    );
    await page.waitForTimeout(2500);
    await page.evaluate(() => {
      if (typeof window.__deckFreezeReveals === 'function') window.__deckFreezeReveals();
    });
    await page.emulateMedia({ media: 'screen' });
    const buf = await page.pdf({
      width: `${W}px`,
      height: `${H}px`,
      printBackground: true,
      margin: { top: 0, right: 0, bottom: 0, left: 0 },
    });
    pageBuffers.push(buf);
    await page.close();
    console.log(`  [${pageBuffers.length}/${files.length}] ${f}`);
  }
  await browser.close();

  const merged = await PDFDocument.create();
  for (const buf of pageBuffers) {
    const src = await PDFDocument.load(buf);
    const copied = await merged.copyPages(src, src.getPageIndices());
    copied.forEach((p) => merged.addPage(p));
  }
  await fs.writeFile(OUT_FILE, await merged.save());
  console.log(`\n✓ 已生成 ${OUT_FILE}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
