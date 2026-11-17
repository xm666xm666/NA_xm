from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_FILES = (
    PROJECT_ROOT / "static/na-ui.js",
    PROJECT_ROOT / "static/na-theme.js",
    PROJECT_ROOT / "static/index.html",
    PROJECT_ROOT / "static/agent_ui.html",
    PROJECT_ROOT / "static/summary_ui.html",
    PROJECT_ROOT / "static/overview_ui.html",
    PROJECT_ROOT / "static/upstream_ui.html",
    PROJECT_ROOT / "static/upstream_create_ui.html",
    PROJECT_ROOT / "static/bill_ui.html",
    PROJECT_ROOT / "static/platform_ui.html",
    PROJECT_ROOT / "batch/static/index.html",
)


def _node() -> str:
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node.js is required for frontend security checks")
    return executable


def test_shared_escape_html_neutralizes_markup_and_attribute_delimiters() -> None:
    script = r"""
const fs = require("fs");
const vm = require("vm");
const context = { window: { location: { origin: "https://na.example.com" } } };
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
const malicious = `&<>"'<img src=x onerror="alert(1)">`;
const escaped = context.window.NAUi.escapeHtml(malicious);
if (escaped !== "&amp;&lt;&gt;&quot;&#39;&lt;img src=x onerror=&quot;alert(1)&quot;&gt;") {
  throw new Error(`Unexpected escape result: ${escaped}`);
}
if (context.window.NAUi.escapeHtml(null) !== "" || context.window.NAUi.escapeHtml(undefined) !== "") {
  throw new Error("Nullish values must render as empty strings");
}
"""
    subprocess.run(
        [_node(), "-e", script, str(PROJECT_ROOT / "static/na-ui.js")],
        check=True,
        capture_output=True,
        text=True,
    )


def test_postmessage_never_uses_a_wildcard_target_origin() -> None:
    offenders = []
    for path in FRONTEND_FILES:
        source = path.read_text(encoding="utf-8")
        if "postMessage" not in source:
            continue
        if re.search(r"postMessage[\s\S]{0,800}?\}\s*,\s*['\"]\*['\"]\s*\)", source):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))
        assert "'*'" not in source and '"*"' not in source, path
    assert not offenders


def test_every_window_message_listener_has_an_origin_guard() -> None:
    listener_pattern = re.compile(r"(?:window|global)\.addEventListener\(\s*['\"]message['\"]")
    origin_pattern = re.compile(r"\w+\.origin\s*!==\s*(?:window\.|global\.)?location\.origin")
    for path in FRONTEND_FILES:
        source = path.read_text(encoding="utf-8")
        listener_count = len(listener_pattern.findall(source))
        if listener_count:
            assert len(origin_pattern.findall(source)) == listener_count, path


def test_dynamic_html_regressions_use_the_shared_escape_helper() -> None:
    batch = (PROJECT_ROOT / "batch/static/index.html").read_text(encoding="utf-8")
    assert "function escapeLogHtml(value) {\n      return NAUi.escapeHtml(value);" in batch
    assert "const name = NAUi.escapeHtml(item.name || '');" in batch
    assert "const group = NAUi.escapeHtml(item.group || '');" in batch
    assert "<strong>${group}</strong>" not in batch
    assert ".replace(/</g, '&lt;')" not in batch

    for relative in ("static/summary_ui.html", "static/overview_ui.html"):
        source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert re.search(r"function (?:escapeHtml|esc)\(\w+\)\s*\{\s*return NAUi\.escapeHtml\(\w+\);", source)


class _InlineScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[str] = []
        self._capture = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attributes = dict(attrs)
        script_type = (attributes.get("type") or "").strip().lower()
        self._capture = not attributes.get("src") and script_type in {"", "text/javascript", "application/javascript"}
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capture:
            self.scripts.append("".join(self._parts))
            self._capture = False
            self._parts = []


def test_first_party_inline_javascript_is_syntactically_valid() -> None:
    scripts = []
    for path in FRONTEND_FILES:
        if path.suffix != ".html":
            continue
        parser = _InlineScriptParser()
        parser.feed(path.read_text(encoding="utf-8"))
        for index, source in enumerate(parser.scripts, start=1):
            scripts.append({"filename": f"{path.name}#inline-{index}", "source": source})

    checker = r"""
const fs = require("fs");
const vm = require("vm");
const scripts = JSON.parse(fs.readFileSync(0, "utf8"));
for (const item of scripts) new vm.Script(item.source, { filename: item.filename });
"""
    subprocess.run(
        [_node(), "-e", checker],
        input=json.dumps(scripts),
        check=True,
        capture_output=True,
        text=True,
    )
