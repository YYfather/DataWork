#!/usr/bin/env python3
"""在服务器本机交互式保存 DataWork 共享 AI 配置。"""

from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path
import sys


PROVIDER_CHOICES = [
    ("deepseek", "DeepSeek", "https://api.deepseek.com", True),
    ("openai", "OpenAI", "https://api.openai.com/v1", True),
    ("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta", True),
    ("ollama", "Ollama（服务器本地模型）", "http://127.0.0.1:11434/api", False),
    ("openai_compatible", "OpenAI 兼容接口", "http://127.0.0.1:8000/v1", False),
]


def prompt_value(label: str, default: str = "", *, required: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label}{suffix}：").strip() or default
        if value or not required:
            return value
        print(f"{label}不能为空。")


def main() -> int:
    parser = argparse.ArgumentParser(description="配置 DataWork 服务器共享 AI")
    parser.add_argument("--app-dir", default="/www/wwwroot/1490473838.cn/datework")
    args = parser.parse_args()

    app_dir = Path(args.app_dir).expanduser().resolve()
    if not (app_dir / "datawork").is_dir():
        print(f"错误：未找到 DataWork 程序目录：{app_dir}", file=sys.stderr)
        return 1
    sys.path.insert(0, str(app_dir))

    from datawork.ai.provider import ProviderKind
    from datawork.ai.settings import AISettings, AISettingsService, SecretStorage
    from datawork.infrastructure.paths import resolve_workspace_paths

    service = AISettingsService(resolve_workspace_paths(app_dir / "data" / "server_ai"))
    existing = service.load()
    existing_provider = existing.provider.value
    default_index = next(
        (index for index, item in enumerate(PROVIDER_CHOICES, start=1) if item[0] == existing_provider),
        1,
    )

    print("\nDataWork 服务器共享 AI 配置")
    print("API 密钥只会写入服务器本机，不会写入网页、补丁包或日志。")
    for index, (_, label, _, _) in enumerate(PROVIDER_CHOICES, start=1):
        print(f"  {index}. {label}")
    while True:
        raw_choice = input(f"请选择服务商 [{default_index}]：").strip() or str(default_index)
        if raw_choice.isdigit() and 1 <= int(raw_choice) <= len(PROVIDER_CHOICES):
            break
        print("请输入列表中的数字。")

    provider_name, provider_label, preset_url, requires_key = PROVIDER_CHOICES[int(raw_choice) - 1]
    same_provider = provider_name == existing_provider
    base_default = existing.base_url if same_provider and existing.base_url else preset_url
    model_default = existing.model if same_provider else ""
    base_url = prompt_value("API 地址", base_default, required=True)
    model = prompt_value("Model ID", model_default, required=True)

    existing_key = service.resolve_api_key(ProviderKind(provider_name)) if same_provider else ""
    if requires_key:
        hint = "（直接回车保留现有密钥）" if existing_key else ""
        api_key = getpass(f"API 密钥{hint}：").strip()
        if not api_key and not existing_key:
            print("错误：该服务商需要 API 密钥。", file=sys.stderr)
            return 1
    else:
        api_key = getpass("API 密钥（没有可直接回车）：").strip()

    settings = AISettings(
        enabled=True,
        provider=ProviderKind(provider_name),
        base_url=base_url,
        model=model,
        privacy_mode="metadata_only",
        remember_key=True,
        timeout_seconds=existing.timeout_seconds if same_provider else 120,
        max_retries=existing.max_retries if same_provider else 2,
        temperature=existing.temperature if same_provider else 0.3,
        max_tokens=existing.max_tokens if same_provider else 2048,
        allow_no_api_key=not requires_key and not api_key,
    )
    service.save(
        settings,
        api_key=api_key or None,
        secret_storage=SecretStorage.SERVER_FILE,
    )

    status = service.public_status()
    if not status["configured"]:
        print("错误：配置未达到可用状态，请重新运行本脚本。", file=sys.stderr)
        return 1
    print("\n配置完成：")
    print(f"  服务商：{provider_label}")
    print(f"  Model ID：{model}")
    print(f"  非敏感设置：{service.config_path}")
    print(f"  密钥文件：{service.server_secret_path}（脚本随后会设为 600 权限）")
    print("  匿名访客：每个浏览器会话 10 次，首次提问满 24 小时重置")
    print("  工作区认证或填写个人 API 后：不受上述次数限制")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
