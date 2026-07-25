#!/usr/bin/env python3
"""Build the static-only V1.5 pairing test notice server hotfix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "DataWork-v1.5.0-v1.5.0-配对功能测试公告-服务器热补丁"
BUILD_ROOT = ROOT.parent / ".build-artifacts"
DEFAULT_OUTPUT = BUILD_ROOT / PACKAGE_NAME
STATIC_SOURCE = ROOT / "datawork" / "web" / "static"
PATCH_ID = "datawork_v1.5_pairing_test_notice_20260723"
OLD_ASSETS = (
    "assets/index-BpjhpLDa.css",
    "assets/index-DR4Uk53p.js",
)
BASELINE_SHA256 = {
    "index.html": "55c68f429b41de020ef9fc6b64e5150212894b4d4fa11ff8692ca1eecb9abe1d",
    "assets/index-BpjhpLDa.css": "89afb5405ba2f61c08cb6e6b4915edd39fe7e220bdc6e6a9586d8ed680836e1b",
    "assets/index-DR4Uk53p.js": "b4e9ac8abf92f6e7498149dea7349ba94299d0563d53007676955fa66ff963dc",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def referenced_static_files() -> list[Path]:
    index = STATIC_SOURCE / "index.html"
    html = index.read_text(encoding="utf-8")
    references = sorted(set(re.findall(r"/(assets/[^\"']+)", html)))
    files = [index, *(STATIC_SOURCE / reference for reference in references)]
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise SystemExit(f"构建产物缺失：{missing}")
    return files


def manifest(mapping: dict[str, str]) -> str:
    return "".join(f"{digest}  {relative}\n" for relative, digest in sorted(mapping.items()))


def installer_script() -> str:
    old_assets = "\n".join(f'  "{item}"' for item in OLD_ASSETS)
    return f"""#!/usr/bin/env bash
set -Eeuo pipefail

umask 022
PATCH_DIR="$(cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")" && pwd)"
APP_DIR="${{DATAWORK_APP_DIR:-/www/wwwroot/1490473838.cn/datework}}"
STATIC_DIR="$APP_DIR/datawork/web/static"
PAYLOAD_DIR="$PATCH_DIR/payload/datawork/web/static"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_MARKER="$APP_DIR/updates/.last_v15_notice_hotfix_backup"
HEALTH_URL="${{DATAWORK_HEALTH_URL:-http://127.0.0.1:8765/api/health}}"
PAGE_URL="${{DATAWORK_PAGE_URL:-http://127.0.0.1:8765/}}"
OLD_ASSETS=(
{old_assets}
)

log() {{ printf '[DataWork V1.5 公告热补丁] %s\\n' "$*"; }}
fail() {{ printf '[DataWork V1.5 公告热补丁] 错误：%s\\n' "$*" >&2; exit 1; }}

manifest_matches() {{
  local root="$1" manifest_file="$2" expected="" relative="" actual=""
  while read -r expected relative; do
    [[ -n "$expected" && -n "$relative" ]] || continue
    [[ -f "$root/$relative" ]] || return 1
    actual="$(sha256sum "$root/$relative" | awk '{{print $1}}')"
    [[ "$actual" == "$expected" ]] || return 1
  done < "$manifest_file"
}}

[[ "$(id -u)" -eq 0 || "${{DATAWORK_ALLOW_NON_ROOT_TEST:-0}}" == "1" ]] \
  || fail "请使用 root 用户运行。"
[[ -d "$APP_DIR" && -d "$STATIC_DIR" ]] || fail "未找到 DataWork：$APP_DIR"
[[ -x "$APP_DIR/.venv/bin/python" ]] || fail "未找到服务器现有 Python 虚拟环境。"
[[ -f "$APP_DIR/VERSION" ]] || fail "缺少 VERSION 文件。"
[[ "$(tr -d '[:space:]' < "$APP_DIR/VERSION")" == "1.5.0" ]] \
  || fail "本补丁只适用于已运行 V1.5.0 的服务器。"

log "校验补丁包完整性……"
(cd "$PATCH_DIR" && sha256sum -c SHA256SUMS.txt >/dev/null) \
  || fail "补丁包 SHA-256 校验失败。"

if manifest_matches "$STATIC_DIR" "$PATCH_DIR/TARGET_SHA256.txt"; then
  log "公告版前端已经安装，无需重复执行。"
  exit 0
fi

manifest_matches "$STATIC_DIR" "$PATCH_DIR/BASELINE_SHA256.txt" \
  || fail "当前网页静态文件不是已审核的 V1.5 基线；未覆盖任何文件。"

timestamp="$(date +%Y%m%d_%H%M%S)"
backup_dir="$BACKUP_ROOT/{PATCH_ID}_$timestamp"
mkdir -p "$backup_dir"
cp -a "$STATIC_DIR" "$backup_dir/static"
printf '%s\\n' "$backup_dir" > "$BACKUP_MARKER"
chmod 0600 "$BACKUP_MARKER"
log "已备份当前网页资源到：$backup_dir"

owner="$(stat -c '%U' "$APP_DIR")"
group="$(stat -c '%G' "$APP_DIR")"
while IFS= read -r -d '' source; do
  relative="${{source#$PAYLOAD_DIR/}}"
  install -D -m 0644 "$source" "$STATIC_DIR/$relative"
done < <(find "$PAYLOAD_DIR" -type f -print0)

for relative in "${{OLD_ASSETS[@]}}"; do
  rm -f -- "$STATIC_DIR/$relative"
done
find "$STATIC_DIR" -type d -empty -delete
chown -R "$owner:$group" "$STATIC_DIR"

manifest_matches "$STATIC_DIR" "$PATCH_DIR/TARGET_SHA256.txt" \
  || fail "覆盖后的网页文件哈希不一致；请运行 ./回滚公告热补丁.sh。"
for relative in "${{OLD_ASSETS[@]}}"; do
  [[ ! -e "$STATIC_DIR/$relative" ]] \
    || fail "旧前端资源仍存在；请运行 ./回滚公告热补丁.sh。"
done

health_json="$(curl -fsS "$HEALTH_URL")" \
  || fail "V1.5 健康接口不可访问；网页文件已更新，可运行回滚脚本恢复。"
printf '%s' "$health_json" | "$APP_DIR/.venv/bin/python" -c \
  'import json,sys; p=json.load(sys.stdin); assert p["status"]=="ok"; assert p["version"]=="1.5.0"; assert p["features"]["pairing_workflow"] is True; assert p["features"]["dependent_variable_groups"] is True' \
  || fail "后端未处于完整 V1.5 状态；请运行 ./回滚公告热补丁.sh。"
page_html="$(curl -fsS "$PAGE_URL")" \
  || fail "服务器网页入口不可访问；请运行 ./回滚公告热补丁.sh。"
grep -q 'index-Cnt-pWU9.js' <<< "$page_html" \
  || fail "服务器尚未返回公告版网页入口；请运行 ./回滚公告热补丁.sh。"

log "更新成功：V1.5 配对功能测试公告与 V1.5 版本显示已上线。"
log "无需重启 Python；请在浏览器按 Ctrl+F5 强制刷新。"
log "备份位置：$backup_dir"
"""


def rollback_script() -> str:
    return f"""#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${{DATAWORK_APP_DIR:-/www/wwwroot/1490473838.cn/datework}}"
STATIC_DIR="$APP_DIR/datawork/web/static"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_MARKER="$APP_DIR/updates/.last_v15_notice_hotfix_backup"

log() {{ printf '[DataWork V1.5 公告热补丁回滚] %s\\n' "$*"; }}
fail() {{ printf '[DataWork V1.5 公告热补丁回滚] 错误：%s\\n' "$*" >&2; exit 1; }}

[[ "$(id -u)" -eq 0 || "${{DATAWORK_ALLOW_NON_ROOT_TEST:-0}}" == "1" ]] \
  || fail "请使用 root 用户运行。"
[[ -f "$BACKUP_MARKER" ]] || fail "没有找到本公告热补丁的备份标记。"
backup_dir="$(tr -d '\\r\\n' < "$BACKUP_MARKER")"
case "$backup_dir" in
  "$BACKUP_ROOT"/{PATCH_ID}_*) ;;
  *) fail "备份路径不在预期目录内，已停止。" ;;
esac
[[ -d "$backup_dir/static" ]] || fail "备份网页目录不存在：$backup_dir/static"

owner="$(stat -c '%U' "$APP_DIR")"
group="$(stat -c '%G' "$APP_DIR")"
replaced="$backup_dir/replaced_static_$(date +%Y%m%d_%H%M%S)"
mv "$STATIC_DIR" "$replaced"
cp -a "$backup_dir/static" "$STATIC_DIR"
chown -R "$owner:$group" "$STATIC_DIR"
rm -f -- "$BACKUP_MARKER"

log "已恢复公告热补丁安装前的网页资源。"
log "被替换的公告版资源保留在：$replaced"
log "请在浏览器按 Ctrl+F5 强制刷新。"
"""


def readme_text(zip_name: str) -> str:
    return f"""# DataWork V1.5 配对功能测试公告热补丁

目标路径：`/www/wwwroot/1490473838.cn/datework`

适用条件：

- 服务器健康接口已经显示 `version=1.5.0`；
- `pairing_workflow=true`；
- `dependent_variable_groups=true`；
- 当前网页仍为首个 V1.5 配对版静态资源。

本补丁只更新网页静态文件：

- 每次打开页面时弹出“配对列仍在测试修补阶段，请谨慎使用”的强制确认公告；
- 页头将服务器 `1.5.0` 格式化显示为 `DATAWORK V1.5`；
- 不修改 Python 核心、虚拟环境、数据库、上传数据、报告或用户配置；
- 不需要重启 Python 服务。

当前状态未发布，仅保留目录源码。正式发布获批后使用 `--release-zip`
生成 ZIP；届时 SHA-256 以同目录的 `{zip_name}.sha256` 文件为准。

安装：

```bash
unzip '{zip_name}'
cd '{PACKAGE_NAME}'
chmod +x 应用公告热补丁.sh 回滚公告热补丁.sh
./应用公告热补丁.sh
```

安装成功后，在浏览器按 `Ctrl+F5` 强制刷新。

回滚：

```bash
./回滚公告热补丁.sh
```
"""


def deterministic_zip(output: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(item for item in output.rglob("*") if item.is_file()):
            relative = Path(PACKAGE_NAME) / path.relative_to(output)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(2026, 7, 23, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if path.suffix == ".sh" else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            bundle.writestr(info, path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 DataWork V1.5 配对功能测试公告热补丁")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--release-zip", action="store_true", help="批准正式发布后生成 ZIP")
    args = parser.parse_args()
    if (ROOT / "VERSION").read_text(encoding="utf-8").strip() != "1.5.0":
        raise SystemExit("当前源码版本必须是 1.5.0")
    output = args.output.expanduser().resolve()
    build_root = BUILD_ROOT.resolve()
    if output == build_root or build_root not in output.parents:
        raise SystemExit(f"输出目录必须位于临时构建目录：{build_root}")

    files = referenced_static_files()
    target = {
        path.relative_to(STATIC_SOURCE).as_posix(): sha256(path)
        for path in files
    }
    expected = {"index.html", "assets/index-Cnt-pWU9.js", "assets/index-exXYDQAE.css"}
    if set(target) != expected:
        raise SystemExit(f"公告版构建文件与已验证清单不一致：{sorted(target)}")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    payload = output / "payload" / "datawork" / "web" / "static"
    for source in files:
        destination = payload / source.relative_to(STATIC_SOURCE)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    (output / "BASELINE_SHA256.txt").write_text(
        manifest(BASELINE_SHA256),
        encoding="utf-8",
        newline="\n",
    )
    (output / "TARGET_SHA256.txt").write_text(
        manifest(target),
        encoding="utf-8",
        newline="\n",
    )
    apply_script = output / "应用公告热补丁.sh"
    rollback = output / "回滚公告热补丁.sh"
    apply_script.write_text(installer_script(), encoding="utf-8", newline="\n")
    rollback.write_text(rollback_script(), encoding="utf-8", newline="\n")
    os.chmod(apply_script, 0o755)
    os.chmod(rollback, 0o755)
    (output / "安装说明.md").write_text(
        readme_text(f"{PACKAGE_NAME}.zip"),
        encoding="utf-8",
    )
    common_status = {
        "release_status": "unreleased",
        "artifact_policy": "source-directory-only; ZIP and sidecar are generated only for an approved release",
    }
    (output / "PATCH_INFO.json").write_text(
        json.dumps(
            {
                "patch_id": PATCH_ID,
                "version": "1.5.0",
                "package_name": PACKAGE_NAME,
                "accepted_versions": ["1.5.0"],
                "scope": "web-static-only pairing test notice",
                **common_status,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output / "PACKAGE_VERIFICATION.json").write_text(
        json.dumps(
            {
                "baseline_static_files": len(BASELINE_SHA256),
                "target_static_files": len(target),
                "status": "source directory verified; release ZIP not generated",
                **common_status,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    checksums = {
        path.relative_to(output).as_posix(): sha256(path)
        for path in output.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    }
    (output / "SHA256SUMS.txt").write_text(
        manifest(checksums),
        encoding="utf-8",
        newline="\n",
    )

    print(f"package={output}")
    if args.release_zip:
        archive = output.parent / f"{PACKAGE_NAME}.zip"
        if archive.exists():
            archive.unlink()
        deterministic_zip(output, archive)
        archive_digest = sha256(archive)
        checksum_file = archive.with_suffix(".zip.sha256")
        checksum_file.write_text(
            f"{archive_digest}  {archive.name}\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"zip={archive}")
        print(f"sha256={archive_digest}")
        print(f"size={archive.stat().st_size}")
    else:
        print("release_status=unreleased; zip=not-generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
