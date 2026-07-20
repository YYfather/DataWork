import json
from pathlib import Path


def test_tauri_sidecar_scaffold_is_complete():
    project_root = Path(__file__).resolve().parents[2]
    root = project_root / "desktop"
    version = (project_root / "VERSION").read_text(encoding="utf-8").strip()
    config = json.loads((root / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    assert config["version"] == version
    assert config["bundle"]["externalBin"] == ["binaries/datawork-sidecar"]
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
    assert (project_root / "scripts" / "package_portable.py").exists()
    source_packager = (project_root / "scripts" / "package_source.py").read_text(encoding="utf-8")
    assert '("desktop", "src-tauri", "binaries")' in source_packager
