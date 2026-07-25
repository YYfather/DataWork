from __future__ import annotations

import hashlib

from scripts.package_website_deployment import (
    BUILD_ROOT,
    DEFAULT_OUTPUT,
    copy_hotfix_sources,
    deployment_sha256,
    write_manifest,
)


def test_deployment_manifest_uses_linux_line_endings_for_text(tmp_path) -> None:
    text_file = tmp_path / "README.md"
    text_file.write_bytes(b"first\r\nsecond\r\n")
    assert deployment_sha256(text_file) == hashlib.sha256(b"first\nsecond\n").hexdigest()


def test_deployment_manifest_keeps_binary_bytes_exact(tmp_path) -> None:
    archive = tmp_path / "patch.zip"
    archive.write_bytes(b"PK\r\n\x00binary")
    assert deployment_sha256(archive) == hashlib.sha256(archive.read_bytes()).hexdigest()


def test_deployment_manifest_excludes_runtime_caches(tmp_path) -> None:
    (tmp_path / "README.md").write_text("release\n", encoding="utf-8")
    cache = tmp_path / ".pytest_cache"
    cache.mkdir()
    (cache / "README.md").write_text("cache\n", encoding="utf-8")

    write_manifest(tmp_path)

    manifest = (tmp_path / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert "README.md" in manifest
    assert ".pytest_cache" not in manifest


def test_deployment_manifest_includes_nested_manifest(tmp_path) -> None:
    nested = tmp_path / "hotfix"
    nested.mkdir()
    (nested / "SHA256SUMS.txt").write_text("nested\n", encoding="utf-8")

    write_manifest(tmp_path)

    manifest = (tmp_path / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert "hotfix/SHA256SUMS.txt" in manifest


def test_deployment_output_uses_external_build_artifacts() -> None:
    assert DEFAULT_OUTPUT.parent == BUILD_ROOT
    assert BUILD_ROOT.name == ".build-artifacts"


def test_copy_hotfix_sources_excludes_archives_and_sidecars(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    package = source / "DataWork-v1.5.0-v1.7.0-test"
    package.mkdir()
    (package / "PATCH_INFO.json").write_text("{}\n", encoding="utf-8")
    (source / "README.md").write_text("index\n", encoding="utf-8")
    (source / "test.zip").write_bytes(b"archive")
    (source / "test.zip.sha256").write_text("digest\n", encoding="utf-8")

    destination = tmp_path / "destination"
    copy_hotfix_sources(source, destination)

    assert (destination / package.name / "PATCH_INFO.json").is_file()
    assert (destination / "README.md").is_file()
    assert not (destination / "test.zip").exists()
    assert not (destination / "test.zip.sha256").exists()
