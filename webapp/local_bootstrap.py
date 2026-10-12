"""本机 BAT 启动所需的安全初始配置。

容器生产环境由 Compose 或 Kubernetes 注入环境变量；本模块只为直接运行
run.bat 的首次本机启动创建可恢复的 .env 配置。
"""

from __future__ import annotations

import os
import secrets
import string
from dataclasses import dataclass
from pathlib import Path


ENV_FILE_NAME = ".env"


@dataclass(frozen=True)
class LocalBootstrapResult:
    env_path: Path
    created_file: bool
    generated_admin_password: str | None


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_project_env(root_dir: Path) -> bool:
    """载入 .env 中未在进程环境设置的变量，显式环境变量优先。"""

    values = _read_env_file(root_dir / ENV_FILE_NAME)
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return bool(values)


def _random_value(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def ensure_local_bootstrap_env(root_dir: Path) -> LocalBootstrapResult:
    """为 run.bat 创建首次本机登录所需的 .env，绝不覆盖已有值。"""

    env_path = root_dir / ENV_FILE_NAME
    values = _read_env_file(env_path)
    effective_env = os.environ.get("APP_ENV") or values.get("APP_ENV", "")
    if effective_env.lower() == "production":
        raise RuntimeError("APP_ENV=production 时不可自动生成管理员密码，请通过部署 Secret 配置。")

    created_file = not env_path.exists()
    generated_password: str | None = None
    additions: list[tuple[str, str]] = []
    defaults = {
        "APP_ENV": "development",
        "WEB_AUTO_CREATE_SCHEMA": "true",
        "BOOTSTRAP_ADMIN_EMAIL": "admin@localhost.invalid",
    }
    for key, value in defaults.items():
        if not values.get(key) and not os.environ.get(key):
            additions.append((key, value))

    if not values.get("APP_SECRET_KEY") and not os.environ.get("APP_SECRET_KEY"):
        additions.append(("APP_SECRET_KEY", _random_value(48)))

    if not values.get("BOOTSTRAP_ADMIN_PASSWORD") and not os.environ.get("BOOTSTRAP_ADMIN_PASSWORD"):
        generated_password = _random_value(24)
        additions.append(("BOOTSTRAP_ADMIN_PASSWORD", generated_password))

    if created_file:
        content = [
            "# 由 run.bat 在首次本机启动时生成；包含本机管理员凭据，禁止提交到 Git。",
            *[f"{key}={value}" for key, value in additions],
            "",
        ]
        env_path.write_text("\n".join(content), encoding="utf-8")
    elif additions:
        with env_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n# 以下本机启动配置由 run.bat 自动补齐。\n")
            for key, value in additions:
                handle.write(f"{key}={value}\n")

    return LocalBootstrapResult(
        env_path=env_path,
        created_file=created_file,
        generated_admin_password=generated_password,
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="初始化本机网站管理员配置")
    parser.add_argument("--ensure", action="store_true", help="确保 .env 和初始管理员密码存在")
    args = parser.parse_args()
    if not args.ensure:
        parser.print_help()
        return 0

    result = ensure_local_bootstrap_env(Path.cwd())
    if result.generated_admin_password:
        print("[LOCAL ADMIN] 首次本机管理员已准备完成")
        print("[LOCAL ADMIN] 用户名: admin")
        print(f"[LOCAL ADMIN] 初始密码: {result.generated_admin_password}")
        print(f"[LOCAL ADMIN] 凭据已保存至: {result.env_path}")
        print("[LOCAL ADMIN] 首次登录后请按页面提示修改密码。")
    else:
        print(f"[LOCAL ADMIN] 已读取本机配置: {result.env_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
