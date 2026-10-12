#!/usr/bin/env python3
"""Remove all ambient / watermark decorative layers from slide HTML."""
import re
import glob
import os

BASE = os.path.join(os.path.dirname(__file__), "..", "slides")

FRAGMENTS = [
    re.compile(r"\s*<div class=\"ambient-grid\"[^>]*></div>\s*", re.DOTALL),
    re.compile(r"\s*<div class=\"ambient-arc[^\"]*\"[^>]*></div>\s*", re.DOTALL),
    re.compile(r"\s*<div class=\"ambient-beam[^\"]*\"[^>]*></div>\s*", re.DOTALL),
    re.compile(r"\s*<svg class=\"ambient-svg\"[^>]*>.*?</svg>\s*", re.DOTALL),
    re.compile(r"\s*<div class=\"big-num\"[^>]*>.*?</div>\s*", re.DOTALL),
]


def remove_ambient_block(text: str) -> str:
    while True:
        m = re.search(r'<div class="ambient"', text)
        if not m:
            break
        start = m.start()
        i = m.end()
        depth = 1
        while i < len(text) and depth > 0:
            next_open = text.find("<div", i)
            next_close = text.find("</div>", i)
            if next_close == -1:
                text = text[:start] + "\n" + text[m.end():]
                break
            if next_open != -1 and next_open < next_close:
                depth += 1
                i = next_open + 4
            else:
                depth -= 1
                i = next_close + 6
        else:
            text = text[:start] + "\n" + text[i:]
    return text


def clean(text: str) -> str:
    text = remove_ambient_block(text)
    for pat in FRAGMENTS:
        text = pat.sub("\n", text)
    text = re.sub(r"\s*</div>\s*(?=<header)", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


for path in sorted(glob.glob(os.path.join(BASE, "*.html"))):
    raw = open(path, encoding="utf-8").read()
    updated = clean(raw)
    if updated != raw:
        open(path, "w", encoding="utf-8").write(updated)
        print("cleaned", os.path.basename(path))

print("done")
