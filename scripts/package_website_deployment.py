#!/usr/bin/env python3
"""从当前源码和个人主页副本生成未压缩的宝塔网站部署分支。"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
DEFAULT_LEGACY_PACKAGE = ROOT / "发布包" / f"DataWork-v{VERSION}-网站部署安装包.zip"
DEFAULT_OUTPUT = ROOT / "发布包" / f"DataWork-v{VERSION}-网站部署版本"
DEFAULT_WEB_ROOT = Path(r"E:\studywork\Web")
SKIP_WEB_PARTS = {".git", ".agents", ".jj", ".reasonix", "node_modules"}
SKIP_RUNTIME_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SCRIPT_NAMES = ("服务器环境准备.sh", "设置工作区密码.sh")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成未压缩 DataWork 网站部署目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--website-root", type=Path, default=DEFAULT_WEB_ROOT)
    parser.add_argument("--legacy-package", type=Path, default=DEFAULT_LEGACY_PACKAGE)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for entry in archive.infolist():
        target = (destination / entry.filename).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(f"归档包含越界路径：{entry.filename}") from exc
        if entry.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(entry) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)


def copy_tree(source: Path, destination: Path, *, skip_parts: set[str]) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in skip_parts or name.endswith((".pyc", ".pyo", ".log", ".tmp"))}

    shutil.copytree(source, destination, ignore=ignore)


def write_manifest(root: Path) -> None:
    lines = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_file() and path.name != "SHA256SUMS.txt" and ".git" not in path.parts:
            lines.append(f"{sha256(path)}  {path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    args = parse_args()
    output = args.output.expanduser().resolve()
    web_root = args.website_root.expanduser().resolve()
    legacy = args.legacy_package.expanduser().resolve()
    if not web_root.is_dir():
        raise SystemExit(f"个人主页目录不存在：{web_root}")
    if not legacy.is_file():
        raise SystemExit(f"未找到旧网站部署包，无法保留既有宝塔配置：{legacy}")
    if output == ROOT or ROOT not in output.parents:
        raise SystemExit(f"拒绝写入工作区外或工作区根目录：{output}")

    with tempfile.TemporaryDirectory(prefix="datawork-web-deploy-") as raw_temp:
        staging_parent = Path(raw_temp)
        with zipfile.ZipFile(legacy) as archive:
            safe_extract(archive, staging_parent)
        extracted = staging_parent / f"DataWork-v{VERSION}-网站部署安装包"
        if not extracted.is_dir():
            raise RuntimeError("旧网站部署包目录结构不符合预期")

        service_old = extracted / "DataWork服务"
        preserved: dict[str, bytes] = {}
        for name in (*SCRIPT_NAMES, "workspace_auth.json", "requirements.txt", "宝塔面板部署说明.txt"):
            candidate = service_old / name
            if candidate.is_file():
                preserved[name] = candidate.read_bytes()

        service_old.mkdir(exist_ok=True)
        shutil.rmtree(service_old)
        service = extracted / "DataWork服务"
        service.mkdir()
        for name in ("README.md", "VERSION", "pyproject.toml"):
            shutil.copy2(ROOT / name, service / name)
        requirements = ROOT / "requirements.txt"
        if requirements.is_file():
            shutil.copy2(requirements, service / "requirements.txt")
        elif "requirements.txt" in preserved:
            (service / "requirements.txt").write_bytes(preserved["requirements.txt"])
        else:
            raise RuntimeError("缺少 requirements.txt")
        shutil.copy2(ROOT / "deploy" / "linux-server" / "bt_start.py", service / "bt_start.py")
        copy_tree(ROOT / "datawork", service / "datawork", skip_parts=SKIP_RUNTIME_PARTS)

        for name in (*SCRIPT_NAMES, "workspace_auth.json", "宝塔面板部署说明.txt"):
            if name in preserved:
                (service / name).write_bytes(preserved[name])

        patch_root = ROOT / "发布包" / f"DataWork-v{VERSION}-服务器AI共享与额度控制-热补丁"
        for name in ("设置服务器AI配置.sh", "configure_server_ai.py"):
            source = patch_root / name
            if source.is_file():
                shutil.copy2(source, service / name)

        homepage = extracted / "主页完整副本"
        if homepage.exists():
            shutil.rmtree(homepage)
        copy_tree(web_root, homepage, skip_parts=SKIP_WEB_PARTS)
        (extracted / "请先阅读.txt").write_text(
            f"""DataWork {VERSION} 网站部署版本（未压缩目录）
============================================

本目录是个人主页与 DataWork 服务的部署分支，不是通用源码包。

1. 主页完整副本：来自 E:\\studywork\\Web 的部署用副本，未修改原目录。
2. 主页增量覆盖：保留原有 /datework 入口增量文件；迁移时按其中说明覆盖主页。
3. DataWork服务：来自当前 DataWork 源码，包含工作区认证、最多 3 个活跃用户、
   AI 访客额度（10 次/24 小时）和服务器 AI 配置能力。
4. 服务器不包含 API 密钥、用户数据库、上传数据或报告；请在服务器本机运行配置脚本。
5. 宝塔部署顺序见 DataWork服务/宝塔面板部署说明.txt。

请直接上传本目录的相应子目录，不需要解压本目录。
文件清单与 SHA-256 位于 SHA256SUMS.txt。
""",
            encoding="utf-8",
            newline="\n",
        )
        write_manifest(extracted)

        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(extracted, output)

    print(f"网站部署目录：{output}")
    print(f"文件数量：{sum(1 for item in output.rglob('*') if item.is_file())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
