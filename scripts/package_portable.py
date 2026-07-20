"""把当前平台 sidecar 封装为可直接分发的便携程序 ZIP。"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import platform
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    suffix = ".exe" if sys.platform.startswith("win") else ""
    parser.add_argument(
        "--artifact",
        type=Path,
        default=ROOT / "dist" / f"datawork-sidecar{suffix}",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / "release")
    args = parser.parse_args()

    artifact = args.artifact.resolve()
    if not artifact.is_file():
        raise SystemExit(f"sidecar 不存在: {artifact}")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    system = platform.system() or "Unknown"
    architecture = "x64" if platform.machine().lower() in {"amd64", "x86_64"} else platform.machine()
    executable_name = "DataWork.exe" if suffix else "DataWork"
    package_name = f"DataWork-v{version}-{system}-{architecture}-portable.zip"
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    package = output_dir / package_name
    executable_hash = _sha256(artifact)
    readme = f"""DataWork {version} 便携版

使用方法：
1. 解压整个 ZIP；
2. 双击 {executable_name}；
3. 程序启动本地统计服务并自动打开浏览器；
4. 使用期间不要关闭程序窗口，关闭后本地服务随即停止。

说明：
- 不需要另行安装 Python、Node.js 或统计依赖；
- 默认只监听 127.0.0.1，不向局域网开放；
- 用户项目保存在系统用户数据目录，不写入程序目录；
- 首次启动需要解压单文件运行环境，可能等待十余秒；
- AI API 密钥不包含在程序包中，需要用户自行配置。

文件校验：
SHA-256 ({executable_name}) = {executable_hash}
"""
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        bundle.write(artifact, executable_name)
        bundle.writestr("README.txt", readme)
        bundle.writestr("SHA256SUMS.txt", f"{executable_hash}  {executable_name}\n")
    package_hash = _sha256(package)
    package.with_suffix(package.suffix + ".sha256").write_text(
        f"{package_hash}  {package.name}\n", encoding="utf-8"
    )
    print(f"便携版已生成: {package}")
    print(f"SHA-256: {package_hash}")


if __name__ == "__main__":
    main()
