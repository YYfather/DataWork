from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import zipfile


def _assert_manifest(archive: zipfile.ZipFile, root: str, manifest_name: str) -> None:
    import hashlib

    manifest = archive.read(root + manifest_name).decode("utf-8").splitlines()
    assert manifest
    for line in manifest:
        expected, relative = line.split("  ", 1)
        assert hashlib.sha256(archive.read(root + relative)).hexdigest() == expected


def test_platform_packager_creates_separated_chinese_packages(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "package_platform_releases.py"),
            "--output-dir",
            str(tmp_path),
            "--skip-windows",
        ],
        cwd=project_root,
        check=True,
    )

    expected = {
        "datework_macos_command.zip",
        "datework_linux_server.zip",
        "datework_source.zip",
    }
    assert expected <= {path.name for path in tmp_path.iterdir()}
    assert all((tmp_path / f"{name}.sha256").is_file() for name in expected)

    with zipfile.ZipFile(tmp_path / "datework_macos_command.zip") as archive:
        root = "datework_macos_command/"
        names = set(archive.namelist())
        install_name = root + "安装 DataWork.command"
        assert install_name in names
        assert root + "启动 DataWork.command" in names
        assert root + "使用说明.txt" in names
        assert root + "datawork/web/static/index.html" in names
        assert "Python 3.11" in archive.read(root + "使用说明.txt").decode("utf-8")
        mode = archive.getinfo(install_name).external_attr >> 16
        assert mode & 0o111
        _assert_manifest(archive, root, "SHA256SUMS.txt")

    with zipfile.ZipFile(tmp_path / "datework_linux_server.zip") as archive:
        root = "datework_linux_server/"
        names = set(archive.namelist())
        assert root + "bt_start.py" in names
        assert root + "requirements.txt" in names
        assert root + "宝塔面板部署说明.txt" in names
        assert root + "datawork/web/static/index.html" in names
        assert root + "Dockerfile" not in names
        assert root + "compose.yaml" not in names
        assert not any(name.endswith(".sh") for name in names)
        launcher = archive.read(root + "bt_start.py").decode("utf-8")
        requirements = archive.read(root + "requirements.txt").decode("utf-8")
        instructions = archive.read(root + "宝塔面板部署说明.txt").decode("utf-8")
        assert 'HOST = "127.0.0.1"' in launcher
        assert "0.0.0.0" not in launcher
        assert "fastapi>=0.115" in requirements
        assert "uvicorn>=0.30" in requirements
        assert "/www/wwwroot/datework" in instructions
        assert "Supervisor" in instructions
        assert "不得将 8765 端口直接开放到公网" in instructions
        _assert_manifest(archive, root, "SHA256SUMS.txt")

    with zipfile.ZipFile(tmp_path / "datework_source.zip") as archive:
        root = "datework_source/"
        names = set(archive.namelist())
        assert root + "使用说明.txt" in names
        assert root + "SOURCE_MANIFEST_SHA256.txt" in names
        assert root + "scripts/package_platform_releases.py" in names
        assert not any("/dist/" in name for name in names)
        assert not any("/desktop/src-tauri/binaries/" in name for name in names)
        _assert_manifest(archive, root, "SOURCE_MANIFEST_SHA256.txt")
