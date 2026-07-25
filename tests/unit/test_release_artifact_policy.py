from __future__ import annotations

from scripts import (
    clean_release_workspace,
    package_server_derived_hotfix,
    package_server_v15_hotfix,
    package_server_v15_notice_hotfix,
    package_server_v17_hotfix,
)


def test_hotfix_builders_default_to_external_build_artifacts() -> None:
    modules = (
        package_server_derived_hotfix,
        package_server_v15_hotfix,
        package_server_v15_notice_hotfix,
        package_server_v17_hotfix,
    )
    for module in modules:
        assert module.DEFAULT_OUTPUT.parent == module.BUILD_ROOT
        assert module.BUILD_ROOT.name == ".build-artifacts"
        assert clean_release_workspace.ROOT not in module.DEFAULT_OUTPUT.parents


def test_old_release_cleanup_targets_complete_release_directory(tmp_path, monkeypatch) -> None:
    release_root = tmp_path / "发布包"
    release_root.mkdir()
    (release_root / "old.zip").write_bytes(b"old")
    monkeypatch.setattr(clean_release_workspace, "ROOT", tmp_path)

    targets = clean_release_workspace.artifact_targets(include_old_releases=True)

    assert release_root in targets
