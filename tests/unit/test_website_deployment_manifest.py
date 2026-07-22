from __future__ import annotations

import hashlib

from scripts.package_website_deployment import deployment_sha256


def test_deployment_manifest_uses_linux_line_endings_for_text(tmp_path) -> None:
    text_file = tmp_path / "README.md"
    text_file.write_bytes(b"first\r\nsecond\r\n")
    assert deployment_sha256(text_file) == hashlib.sha256(b"first\nsecond\n").hexdigest()


def test_deployment_manifest_keeps_binary_bytes_exact(tmp_path) -> None:
    archive = tmp_path / "patch.zip"
    archive.write_bytes(b"PK\r\n\x00binary")
    assert deployment_sha256(archive) == hashlib.sha256(archive.read_bytes()).hexdigest()
