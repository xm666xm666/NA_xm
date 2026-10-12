"""命令行参数测试（无需网络）。"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
BATCH_DIR = AGENT_DIR.parent / "batch"
ROOT_DIR = AGENT_DIR.parent


def _load_agent_main():
    import importlib.util

    spec = importlib.util.spec_from_file_location("agent_cli_main", AGENT_DIR / "main.py")
    if spec is None or spec.loader is None:
        raise ImportError(AGENT_DIR / "main.py")
    inserted = str(AGENT_DIR) not in sys.path
    if inserted:
        sys.path.insert(0, str(AGENT_DIR))
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(str(AGENT_DIR))


agent_main = _load_agent_main()


def _capture(fn):
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = fn()
    return code, out.getvalue(), err.getvalue()


def test_agent_list_llm_providers():
    code, out, _ = _capture(lambda: agent_main.main(["--list-llm-providers"]))
    assert code == 0
    assert "mimo" in out
    assert "ollama" in out


def test_agent_list_llm_providers_json():
    code, out, _ = _capture(lambda: agent_main.main(["--list-llm-providers", "--json"]))
    assert code == 0
    data = json.loads(out)
    ids = {item["id"] for item in data}
    assert "mimo" in ids


def test_agent_extract_volcano_example():
    sample = ROOT_DIR / "examples" / "agent" / "volcano" / "input.txt"
    if not sample.exists():
        return
    proc = subprocess.run(
        [sys.executable, "main.py", "-f", str(sample)],
        cwd=AGENT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ep-" in proc.stdout or "ark-" in proc.stdout


def test_agent_llm_cli_override():
    parser = agent_main.build_parser()
    args = parser.parse_args(
        [
            "--use-llm",
            "--llm-provider",
            "mimo",
            "--llm-api-base",
            "https://api.xiaomimimo.com/v1",
            "--llm-model",
            "mimo-v2.5-pro",
            "-t",
            "demo",
        ]
    )
    cfg = agent_main.build_llm_config(args, {})
    assert cfg["provider"] == "mimo"
    assert cfg["model"] == "mimo-v2.5-pro"


def test_batch_help():
    proc = subprocess.run(
        [sys.executable, "main.py", "-h"],
        cwd=BATCH_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "channel" in proc.stdout
    assert "token" in proc.stdout
    assert "group" in proc.stdout


def test_batch_channel_help_legacy():
    """无子命令时 -h 仍可用（normalize 为 channel --help 前的顶层帮助）。"""
    proc = subprocess.run(
        [sys.executable, "main.py", "channel", "-h"],
        cwd=BATCH_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--base-url" in proc.stdout
    assert "--json" in proc.stdout


def test_agent_extract_token_mode():
    text = "demo-a-uat-m1\n张三\ndemo-a-uat\nm1，m2"
    code, out, _ = _capture(
        lambda: agent_main.main(["--mode", "token", "-t", text])
    )
    assert code == 0, out
    assert "demo-a-uat-m1-张三" in out
    assert "demo-a-uat" in out
    assert "m1,m2" in out


def test_agent_extract_token_json():
    text = "demo-a-uat-m1-张三\ndemo-a-uat\nm1，m2"
    code, out, _ = _capture(
        lambda: agent_main.main(["--mode", "token", "-t", text, "--json"])
    )
    assert code == 0
    data = json.loads(out)
    assert data["success"] is True
    assert data["mode"] == "token_rules"
    assert data["count"] == 1


def test_app_extract_token_subcommand():
    proc = subprocess.run(
        [
            sys.executable,
            "app.py",
            "extract-token",
            "-t",
            "demo-a-uat-m1\n张三\ndemo-a-uat\nm1，m2",
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "demo-a-uat-m1-张三" in proc.stdout


def test_app_batch_token_help():
    proc = subprocess.run(
        [sys.executable, "app.py", "token-batch", "-h"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--base-url" in proc.stdout or "-f" in proc.stdout


def run():
    test_agent_list_llm_providers()
    test_agent_list_llm_providers_json()
    test_agent_extract_volcano_example()
    test_agent_llm_cli_override()
    test_agent_extract_token_mode()
    test_agent_extract_token_json()
    test_batch_help()
    test_batch_channel_help_legacy()
    test_app_extract_token_subcommand()
    test_app_batch_token_help()
    print("all cli tests passed")


if __name__ == "__main__":
    run()
