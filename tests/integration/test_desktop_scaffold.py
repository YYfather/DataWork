import json
from pathlib import Path


def test_tauri_sidecar_scaffold_is_complete():
    project_root = Path(__file__).resolve().parents[2]
    root = project_root / "desktop"
    version = (project_root / "VERSION").read_text(encoding="utf-8").strip()
    config = json.loads((root / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    assert config["version"] == version
    assert config["bundle"]["externalBin"] == ["binaries/datawork-sidecar"]
    assert config["app"]["windows"][0]["maximized"] is True
    windows_bundle = config["bundle"]["windows"]
    assert windows_bundle["wix"]["language"] == "zh-CN"
    assert windows_bundle["nsis"]["languages"] == ["SimpChinese"]
    assert windows_bundle["nsis"]["displayLanguageSelector"] is False
    assert windows_bundle["nsis"]["installMode"] == "currentUser"
    assert (root / "src-tauri" / "src" / "lib.rs").exists()
    assert "/api/health" in (root / "ui" / "index.html").read_text(encoding="utf-8")
    spec = (project_root / "packaging" / "datawork_web.spec").read_text(encoding="utf-8")
    assert "ROOT = Path(SPECPATH).parent" in spec
    assert "parent.parent" not in spec
    assert (project_root / "scripts" / "desktop_entry.py").exists()
    build_script = (project_root / "scripts" / "build_release.py").read_text(encoding="utf-8")
    assert "--reuse-sidecar" in build_script
    assert "smoke_sidecar.py" in build_script
    assert (project_root / "scripts" / "smoke_sidecar.py").exists()
    portable_script = (project_root / "scripts" / "package_portable.py").read_text(encoding="utf-8")
    assert "中文便携版.zip" in portable_script
    assert "解压到任意有写权限的位置" in portable_script
    source_packager = (project_root / "scripts" / "package_source.py").read_text(encoding="utf-8")
    assert '("desktop", "src-tauri", "binaries")' in source_packager
    assert '"target"' in source_packager
    assert (project_root / "scripts" / "package_platform_releases.py").exists()
