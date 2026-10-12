"""NA 渠道 / 令牌信息智能提取 Agent - CLI 入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from lib.channel_extractor import extract_channels
from lib.llm_client import list_provider_presets
from lib.token_extractor import extract_tokens

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

CLI_EXAMPLES = """
示例:
  # 渠道提取
  python main.py -f ../examples/agent/volcano/input.txt
  python main.py -f input.txt --json -o result.json
  python main.py -t "ep-xxx ark-yyy" --use-llm
  python main.py --use-llm --llm-provider mimo --llm-api-key sk-xxx -f input.txt

  # 令牌提取（规则拼接，无 LLM）
  python main.py --mode token -f ../examples/batch/tokens/input.txt
  python main.py --mode token -t "令牌名\\n张三\\ngroup-uat\\nm1，m2"
  python main.py --mode token -f draft.txt --json -o tokens.tsv

  python main.py --list-llm-providers
"""


def load_config(path: Path | None) -> dict[str, Any]:
    cfg_path = path or CONFIG_PATH
    if not cfg_path.exists():
        return {}
    with cfg_path.open(encoding="utf-8") as f:
        return json.load(f)


def read_input_text(args: argparse.Namespace) -> str:
    if args.text and args.file:
        raise SystemExit("不能同时指定 --text 与 --file")
    if args.text:
        return str(args.text)
    if args.file:
        return args.file.read_text(encoding="utf-8")
    if sys.stdin.isatty():
        raise SystemExit("请通过 -f/--file、-t/--text 传入内容，或从 stdin 管道输入")
    return sys.stdin.read()


def build_llm_config(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "api_base": str(args.llm_api_base or config.get("llm_api_base") or "").strip(),
        "api_key": str(args.llm_api_key or config.get("llm_api_key") or "").strip(),
        "model": str(args.llm_model or config.get("llm_model") or "gpt-4o-mini").strip(),
        "provider": str(args.llm_provider or config.get("llm_provider") or "").strip(),
        "timeout": int(args.llm_timeout if args.llm_timeout is not None else config.get("llm_timeout", 60)),
    }


def channel_result_to_dict(result) -> dict[str, Any]:
    return {
        "success": result.success,
        "message": result.message,
        "mode": result.mode,
        "count": result.count,
        "channel_line": result.channel_line,
        "channel_lines": result.channel_lines,
        "fields": result.summary,
        "llm": {
            "enabled": result.llm.enabled,
            "configured": result.llm.configured,
            "invoked": result.llm.invoked,
            "success": result.llm.success,
            "provider": result.llm.provider,
            "model": result.llm.model,
            "items_invoked": result.llm.items_invoked,
            "items_succeeded": result.llm.items_succeeded,
            "items_failed": result.llm.items_failed,
            "filled_fields": result.llm.filled_fields,
            "errors": result.llm.errors,
        },
        "items": [
            {
                "index": item.index,
                "success": item.success,
                "message": item.message,
                "channel_line": item.channel_line,
                "fields": item.summary,
                "sources": item.fields.sources,
                "warnings": item.fields.warnings,
                "confidence": round(item.fields.confidence, 2),
                "llm_invoked": item.fields.llm_invoked,
                "llm_success": item.fields.llm_success,
                "llm_provider": item.fields.llm_provider,
                "llm_model": item.fields.llm_model,
                "llm_filled": item.fields.llm_filled,
                "llm_error": item.fields.llm_error,
            }
            for item in result.items
        ],
    }


def write_output(text: str, output: Path | None) -> None:
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        print(text)


def emit_channel_text_result(result, *, verbose: bool) -> None:
    if result.channel_lines:
        print(result.channel_lines)
    elif result.success:
        print(result.channel_line)
    else:
        print(f"错误: {result.message}", file=sys.stderr)
        for item in result.items:
            if not item.success:
                print(f"  {item.message}", file=sys.stderr)
                if verbose:
                    for key, value in item.summary.items():
                        if value:
                            print(f"    {key}: {value}", file=sys.stderr)
    if verbose and getattr(result, "llm", None):
        llm = result.llm
        if llm.enabled:
            print(
                f"[LLM] enabled={llm.enabled} invoked={llm.invoked} "
                f"provider={llm.provider or '-'} model={llm.model or '-'} "
                f"filled={','.join(llm.filled_fields) or '-'}",
                file=sys.stderr,
            )
            for err in llm.errors:
                print(f"[LLM] {err}", file=sys.stderr)
    if verbose:
        for item in result.items:
            if item.fields.warnings:
                print(f"[#{item.index}] 警告: {'; '.join(item.fields.warnings)}", file=sys.stderr)


def emit_token_text_result(result, *, verbose: bool) -> None:
    if result.token_lines:
        print(result.token_lines)
    elif result.success:
        print(result.token_lines)
    else:
        print(f"错误: {result.message}", file=sys.stderr)
    if verbose:
        for item in result.items:
            status = "OK" if item.success else "FAIL"
            print(f"[{status}] #{item.index} {item.message}", file=sys.stderr)
            if item.success and item.token_line:
                print(f"  {item.token_line}", file=sys.stderr)
        for warn in result.warnings:
            print(f"[警告] {warn}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从杂乱信息提取 NA 渠道行或令牌批量行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_EXAMPLES,
    )
    input_group = parser.add_argument_group("输入")
    input_group.add_argument("-f", "--file", type=Path, help="输入文件")
    input_group.add_argument("-t", "--text", help="直接传入原始文本")
    input_group.add_argument(
        "--mode",
        choices=("channel", "token"),
        default="channel",
        help="提取模式：channel=渠道（默认）；token=令牌（规则拼接，忽略 LLM）",
    )

    config_group = parser.add_argument_group("配置")
    config_group.add_argument("-c", "--config", type=Path, help=f"配置文件路径（默认 {CONFIG_PATH.name}）")

    llm_group = parser.add_argument_group("LLM 增强（仅 --mode channel）")
    llm_group.add_argument("--use-llm", action="store_true", help="启用 LLM 增强（将真实调用 AI，并优先采用 AI 结果）")
    llm_group.add_argument("--llm-provider", help="LLM 厂商预设，如 openai / deepseek / mimo / ollama")
    llm_group.add_argument("--llm-api-base", help="LLM API 地址")
    llm_group.add_argument("--llm-api-key", help="LLM API Key（Ollama 可留空）")
    llm_group.add_argument("--llm-model", help="LLM 模型名")
    llm_group.add_argument("--llm-timeout", type=int, help="LLM 请求超时（秒）")
    llm_group.add_argument(
        "--list-llm-providers",
        action="store_true",
        help="列出支持的 LLM 厂商预设后退出",
    )

    output_group = parser.add_argument_group("输出")
    output_group.add_argument("--json", action="store_true", help="输出 JSON")
    output_group.add_argument("-o", "--output", type=Path, help="写入结果到文件")
    output_group.add_argument("-v", "--verbose", action="store_true", help="输出警告与字段详情到 stderr")
    return parser


def run_token_extract(args: argparse.Namespace) -> int:
    raw_text = read_input_text(args)
    if not raw_text.strip():
        print("错误: 输入内容为空", file=sys.stderr)
        return 1
    if args.use_llm:
        print("提示: 令牌提取为纯规则模式，已忽略 --use-llm", file=sys.stderr)

    result = extract_tokens(raw_text)
    if args.json:
        write_output(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), args.output)
    else:
        if args.output:
            text = result.token_lines or (result.message if not result.success else "")
            write_output(text, args.output)
        else:
            emit_token_text_result(result, verbose=args.verbose)
    return 0 if result.success else 1


def run_channel_extract(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    raw_text = read_input_text(args)
    if not raw_text.strip():
        print("错误: 输入内容为空", file=sys.stderr)
        return 1

    llm_config = build_llm_config(args, config)
    result = extract_channels(raw_text, use_llm=args.use_llm, llm_config=llm_config)

    if args.json:
        payload = json.dumps(channel_result_to_dict(result), ensure_ascii=False, indent=2)
        write_output(payload, args.output)
    else:
        if args.output:
            text = result.channel_lines or (result.channel_line if result.success else "")
            if not text:
                text = result.message
            write_output(text, args.output)
        else:
            emit_channel_text_result(result, verbose=args.verbose)

    return 0 if result.success else 1


def run(args: argparse.Namespace) -> int:
    if args.list_llm_providers:
        presets = list_provider_presets()
        if args.json:
            write_output(json.dumps(presets, ensure_ascii=False, indent=2), args.output)
        else:
            lines = ["可用 LLM 厂商预设:"]
            for item in presets:
                key_hint = "需 Key" if item["api_key_required"] else "Key 可空"
                lines.append(
                    f"  {item['id']:12} {item['label']}  "
                    f"base={item['api_base'] or '-'}  model={item['model']}  ({key_hint})"
                )
            write_output("\n".join(lines), args.output)
        return 0

    mode = str(getattr(args, "mode", "channel") or "channel").strip().lower()
    if mode == "token":
        return run_token_extract(args)
    return run_channel_extract(args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
