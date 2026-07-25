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
BUILD_ROOT = ROOT.parent / ".build-artifacts"
DEFAULT_LEGACY_PACKAGE = ROOT.parent / "DataWork-Web-inspect"
DEFAULT_OUTPUT = BUILD_ROOT / f"DataWork-v{VERSION}-网站部署版本"
DEFAULT_WEB_ROOT = Path(r"E:\studywork\Web")
SKIP_WEB_PARTS = {".git", ".agents", ".jj", ".reasonix", "node_modules"}
SKIP_RUNTIME_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_MANIFEST_PARTS = SKIP_RUNTIME_PARTS | {".git"}
SCRIPT_NAMES = ("服务器环境准备.sh", "设置工作区密码.sh", "设置服务器AI配置.sh")
TEXT_SUFFIXES = {
    ".css",
    ".conf",
    ".html",
    ".ini",
    ".j2",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".php",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_FILENAMES = {".gitignore", ".htaccess", ".prettierignore", ".prettierrc", "VERSION"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成未压缩 DataWork 网站部署目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--website-root", type=Path, default=DEFAULT_WEB_ROOT)
    parser.add_argument("--legacy-package", type=Path, default=DEFAULT_LEGACY_PACKAGE, help="既有网站部署目录或 ZIP")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def deployment_sha256(path: Path) -> str:
    """Hash text with canonical Linux LF endings for the Web branch."""
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_FILENAMES:
        return sha256(path)
    payload = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(payload).hexdigest()


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


def copy_hotfix_sources(source_root: Path, destination_root: Path) -> None:
    """Copy auditable hotfix directories without unpublished archives."""
    if not source_root.is_dir():
        raise RuntimeError(f"服务器工作树缺少热补丁目录：{source_root}")
    destination_root.mkdir()
    for source in sorted(source_root.iterdir()):
        if source.is_dir():
            copy_tree(source, destination_root / source.name, skip_parts=SKIP_RUNTIME_PARTS)
        elif source.name == "README.md":
            shutil.copy2(source, destination_root / source.name)


def write_manifest(root: Path) -> None:
    lines = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        if (
            path.is_file()
            and relative != Path("SHA256SUMS.txt")
            and not SKIP_MANIFEST_PARTS.intersection(relative.parts)
        ):
            lines.append(f"{deployment_sha256(path)}  {relative.as_posix()}")
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    args = parse_args()
    output = args.output.expanduser().resolve()
    web_root = args.website_root.expanduser().resolve()
    legacy = args.legacy_package.expanduser().resolve()
    if not web_root.is_dir():
        raise SystemExit(f"个人主页目录不存在：{web_root}")
    if not legacy.exists() or not (legacy.is_dir() or legacy.is_file()):
        raise SystemExit(f"未找到旧网站部署包，无法保留既有宝塔配置：{legacy}")
    build_root = BUILD_ROOT.resolve()
    if output == build_root or build_root not in output.parents:
        raise SystemExit(f"输出目录必须位于临时构建目录：{build_root}")

    with tempfile.TemporaryDirectory(prefix="datawork-web-deploy-") as raw_temp:
        staging_parent = Path(raw_temp)
        extracted = staging_parent / f"DataWork-v{VERSION}-网站部署安装包"
        if legacy.is_dir():
            copy_tree(legacy, extracted, skip_parts=SKIP_RUNTIME_PARTS | {".git"})
        else:
            with zipfile.ZipFile(legacy) as archive:
                safe_extract(archive, staging_parent)
            candidates = [
                path
                for path in staging_parent.iterdir()
                if path.is_dir() and (path / "DataWork服务").is_dir()
            ]
            if len(candidates) != 1:
                raise RuntimeError("旧网站部署包目录结构不符合预期")
            candidates[0].rename(extracted)

        service_old = extracted / "DataWork服务"
        preserved: dict[str, bytes] = {}
        for name in (*SCRIPT_NAMES, "configure_server_ai.py", "workspace_auth.json", "requirements.txt", "宝塔面板部署说明.txt"):
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

        for name in (*SCRIPT_NAMES, "configure_server_ai.py", "workspace_auth.json", "宝塔面板部署说明.txt"):
            if name in preserved:
                (service / name).write_bytes(preserved[name])

        homepage = extracted / "主页完整副本"
        if homepage.exists():
            shutil.rmtree(homepage)
        copy_tree(web_root, homepage, skip_parts=SKIP_WEB_PARTS)
        hotfix_output = extracted / "热补丁"
        hotfix_source = staging_parent / "hotfix-source"
        if not hotfix_output.is_dir():
            raise RuntimeError(f"服务器部署来源缺少热补丁目录：{hotfix_output}")
        hotfix_output.rename(hotfix_source)
        copy_hotfix_sources(hotfix_source, hotfix_output)

        (extracted / "README.md").write_text(
            f"""# DataWork {VERSION}（V1.7）· Web 部署分支

本分支用于服务器/网站部署，不是通用开发源码。

- `DataWork服务/`：V1.7 Linux/宝塔运行服务，包含配对映射、因变量组合、统一批量任务树和执行审核。
- `主页完整副本/`：个人网站部署副本。
- `主页增量覆盖/`：现有主页的 `/datework` 入口增量文件。
- `宝塔配置/`：Nginx 反向代理和部署检查材料。
- `热补丁/`：保留各版本热补丁的可审计源码目录；ZIP 仅在批准正式发布时生成。
- `SHA256SUMS.txt`：当前分支全部部署文件的 Linux 稳定 SHA-256 清单。

生产工作区密码摘要、API 密钥、用户数据库、上传数据、报告和运行缓存不会进入本分支。
部署后请在服务器本机配置密码及 AI，并按 `DataWork服务/宝塔面板部署说明.txt` 完成权限设置。
""",
            encoding="utf-8",
            newline="\n",
        )

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
6. 热补丁目录保留各版本更新源码目录，已有服务器可按需使用；
   全新部署 DataWork服务 时不需要重复应用主热补丁。
7. 当前状态未发布，不包含 ZIP 或 `.zip.sha256`；正式发布时另行生成并验证。

请直接上传本目录的相应子目录。
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
