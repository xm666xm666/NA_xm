"""New API 批量配置 - 命令行入口（渠道 / 令牌 / 分组）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from lib.batch_processor import run_batch_create
from lib.group_batch_processor import run_group_create
from lib.token_batch_processor import run_token_batch_create
from lib.url_utils import normalize_na_base_url

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.json"

CLI_EXAMPLES = """
示例:
  # 渠道批量（默认；兼容旧用法：直接 -f 即 channel）
  python main.py -c config.json -f ../examples/batch/mixed/input.tsv
  python main.py channel -c config.json -f ../examples/batch/azure/input.tsv
  python main.py --base-url http://localhost:3000 --username admin --password 123456 -f data.tsv

  # 令牌批量
  python main.py token -c config.json -f ../examples/batch/tokens/input.txt
  python main.py token -c config.json -t "name\\tgroup\\tm1,m2" --json

  # 分组批量
  python main.py group -c config.json -f ../examples/batch/groups/input.txt
  python main.py group -c config.json -f groups.txt --ratio 1.0
"""

BATCH_COMMANDS = frozenset({"channel", "token", "group"})


def load_config(path: Path | None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG
    if not cfg_path.exists():
        return {}
    with cfg_path.open(encoding="utf-8") as f:
        return json.load(f)


def read_batch_text(args: argparse.Namespace) -> str:
    if args.text and args.file:
        raise SystemExit("不能同时指定 --text 与 --file")
    if args.text:
        return str(args.text)
    if args.file:
        return args.file.read_text(encoding="utf-8")
    if sys.stdin.isatty():
        raise SystemExit("请通过 -f/--file、-t/--text 传入批量数据，或从 stdin 管道输入")
    return sys.stdin.read()


def resolve_auth(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    access_token = str(args.access_token or config.get("access_token") or "").strip()
    if access_token:
        user_id = args.user_id if args.user_id is not None else config.get("user_id")
        return {"access_token": access_token, "user_id": user_id}
    username = str(args.username or config.get("username") or "").strip()
    password = args.password if args.password is not None else config.get("password", "")
    otp_code = str(getattr(args, "otp_code", None) or config.get("otp_code") or "").strip()
    totp_secret = str(config.get("totp_secret") or config.get("otp_secret") or "").strip()
    auth = {"username": username, "password": password, "otp_code": otp_code}
    if totp_secret:
        auth["totp_secret"] = totp_secret
    return auth


def _success_count(result: Any) -> int:
    if hasattr(result, "success_count"):
        return int(result.success_count)
    # 分组创建结果用 created_count
    return int(getattr(result, "created_count", 0))


def result_to_dict(result) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "total": getattr(result, "total", 0),
        "success_count": _success_count(result),
        "skipped_count": getattr(result, "skipped_count", 0),
        "failed_count": getattr(result, "failed_count", 0),
        "items": getattr(result, "items", []),
    }
    if hasattr(result, "created_count"):
        payload["created_count"] = result.created_count
    if hasattr(result, "groups"):
        payload["groups"] = result.groups
    return payload


def write_output(text: str, output: Path | None) -> None:
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        print(text)


def emit_text_result(result, *, kind: str = "渠道") -> None:
    for item in result.items:
        if item.get("meta"):
            print(f"[信息] 渠道类型来源: {item['type_source']} ({item['type_count']} 项)")
            continue
        if item.get("skipped"):
            print(f"[SKIP] #{item['index']} {item.get('name', '')}: {item['message']}")
            continue
        status = "OK" if item.get("success") else "FAIL"
        print(f"[{status}] #{item['index']} {item.get('name', '')}: {item['message']}")

    created = getattr(result, "created_count", None)
    extra = f" / 新建 {created}" if created is not None else ""
    print(
        f"\n汇总({kind}): 成功 {_success_count(result)}{extra} / 跳过 {result.skipped_count} / "
        f"失败 {result.failed_count} / 共 {result.total}"
    )


def _add_connection_args(parser: argparse.ArgumentParser) -> None:
    config_group = parser.add_argument_group("连接配置")
    config_group.add_argument("-c", "--config", type=Path, help=f"配置文件路径（默认 {DEFAULT_CONFIG.name}）")
    config_group.add_argument("--base-url", help="New API 地址（支持 /console、/api 路径，自动规范化）")
    config_group.add_argument("--username", help="管理员用户名")
    config_group.add_argument("--password", help="管理员密码")
    config_group.add_argument("--otp-code", help="登录两步验证码（认证器 6 位或备用码 8 位）")
    config_group.add_argument("--access-token", help="Access Token（与 --user-id 配合）")
    config_group.add_argument("--user-id", type=int, help="用户 ID（Access Token 模式）")


def _add_input_output_args(parser: argparse.ArgumentParser, *, with_default_key: bool = False) -> None:
    input_group = parser.add_argument_group("输入")
    input_group.add_argument("-f", "--file", type=Path, help="批量数据文件 (TSV/TXT)")
    input_group.add_argument("-t", "--text", help="直接传入批量数据文本")
    if with_default_key:
        input_group.add_argument("--default-key", help="全局渠道密钥（仅渠道批量）")

    output_group = parser.add_argument_group("输出")
    output_group.add_argument("--json", action="store_true", help="输出 JSON")
    output_group.add_argument("-o", "--output", type=Path, help="写入结果到文件")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="New API 批量配置 CLI（渠道 / 令牌 / 分组）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_EXAMPLES,
    )
    sub = parser.add_subparsers(dest="command", metavar="{channel,token,group}")

    channel_p = sub.add_parser("channel", help="批量创建渠道", formatter_class=argparse.RawDescriptionHelpFormatter)
    _add_input_output_args(channel_p, with_default_key=True)
    _add_connection_args(channel_p)

    token_p = sub.add_parser("token", help="批量创建令牌", formatter_class=argparse.RawDescriptionHelpFormatter)
    _add_input_output_args(token_p)
    _add_connection_args(token_p)

    group_p = sub.add_parser("group", help="批量创建分组", formatter_class=argparse.RawDescriptionHelpFormatter)
    _add_input_output_args(group_p)
    _add_connection_args(group_p)
    group_p.add_argument("--ratio", type=float, default=1.0, help="新建分组默认倍率（默认 1.0）")

    return parser


def _resolve_connection(args: argparse.Namespace) -> tuple[str, dict[str, Any], str]:
    config = load_config(args.config)
    base_url = normalize_na_base_url(str(args.base_url or config.get("base_url") or "").strip())
    auth = resolve_auth(args, config)
    default_key = str(getattr(args, "default_key", None) or config.get("default_key") or "").strip()
    if not base_url:
        raise SystemExit("错误: 未配置 New API 地址，请使用 --base-url 或 config.json")
    return base_url, auth, default_key


def _emit_result(args: argparse.Namespace, result: Any, *, kind: str) -> int:
    if args.json:
        payload = json.dumps(result_to_dict(result), ensure_ascii=False, indent=2)
        write_output(payload, args.output)
    else:
        if args.output:
            lines = []
            for item in result.items:
                if item.get("meta"):
                    lines.append(f"[信息] 渠道类型来源: {item['type_source']} ({item['type_count']} 项)")
                    continue
                if item.get("skipped"):
                    lines.append(f"[SKIP] #{item['index']} {item.get('name', '')}: {item['message']}")
                    continue
                status = "OK" if item.get("success") else "FAIL"
                lines.append(f"[{status}] #{item['index']} {item.get('name', '')}: {item['message']}")
            created = getattr(result, "created_count", None)
            extra = f" / 新建 {created}" if created is not None else ""
            lines.append(
                f"\n汇总({kind}): 成功 {_success_count(result)}{extra} / 跳过 {result.skipped_count} / "
                f"失败 {result.failed_count} / 共 {result.total}"
            )
            write_output("\n".join(lines), args.output)
        else:
            emit_text_result(result, kind=kind)
    return 0 if result.failed_count == 0 else 2


def run_channel(args: argparse.Namespace) -> int:
    try:
        base_url, auth, default_key = _resolve_connection(args)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1

    batch_text = read_batch_text(args)
    if not batch_text.strip():
        print("错误: 批量数据为空", file=sys.stderr)
        return 1

    try:
        result = run_batch_create(
            base_url=base_url,
            batch_text=batch_text,
            default_key=default_key,
            auth=auth,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return _emit_result(args, result, kind="渠道")


def run_token(args: argparse.Namespace) -> int:
    try:
        base_url, auth, _ = _resolve_connection(args)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1

    batch_text = read_batch_text(args)
    if not batch_text.strip():
        print("错误: 令牌批量数据为空", file=sys.stderr)
        return 1

    try:
        result = run_token_batch_create(base_url=base_url, batch_text=batch_text, auth=auth)
    except Exception as exc:  # noqa: BLE001
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return _emit_result(args, result, kind="令牌")


def run_group(args: argparse.Namespace) -> int:
    try:
        base_url, auth, _ = _resolve_connection(args)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1

    groups_text = read_batch_text(args)
    if not groups_text.strip():
        print("错误: 分组数据为空", file=sys.stderr)
        return 1

    try:
        result = run_group_create(
            base_url=base_url,
            groups_text=groups_text,
            auth=auth,
            default_ratio=float(args.ratio),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return _emit_result(args, result, kind="分组")


def normalize_argv(argv: list[str] | None) -> list[str]:
    """兼容旧用法：无子命令时默认 channel。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return ["channel", "--help"]
    if args[0] in {"-h", "--help"}:
        return args
    if args[0] not in BATCH_COMMANDS:
        return ["channel", *args]
    return args


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_argv(argv))
    command = args.command or "channel"
    if command == "token":
        return run_token(args)
    if command == "group":
        return run_group(args)
    return run_channel(args)


if __name__ == "__main__":
    raise SystemExit(main())
