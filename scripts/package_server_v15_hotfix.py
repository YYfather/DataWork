#!/usr/bin/env python3
"""Build the verified DataWork V1.5 multi-baseline server hotfix."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
PATCH_ID = "datawork_v1.5_pairing_workflow_20260723"
PACKAGE_NAME = "DataWork-v1.5-配对映射与联合因变量-服务器热补丁-20260723"
DEFAULT_OUTPUT = ROOT / "发布包" / PACKAGE_NAME
ROOT_FILES = ("README.md", "VERSION", "pyproject.toml")
BASELINES = (
    (
        "0.4.9-original",
        ROOT / "web主页本地部分" / "datawork",
    ),
    (
        "0.4.9-derived-hotfix",
        ROOT
        / "发布包"
        / "DataWork-v0.4.9-自定义列与拆分继承-服务器热补丁-20260723"
        / "payload",
    ),
    (
        "1.0.0-website-package",
        ROOT / "发布包" / "DataWork-v1.0-网站部署版本" / "DataWork服务",
    ),
)
ACCEPTED_BASELINE_VERSIONS = ("0.4.9", "1.0.0")
SKIP_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "data",
    "updates",
}
SKIP_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".db", ".sqlite3"}
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".json",
    ".sh",
    ".html",
    ".css",
    ".js",
    ".j2",
}


def sha256(path: Path, *, normalize_text: bool = False) -> str:
    payload = path.read_bytes()
    if normalize_text:
        payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"")
    return hashlib.sha256(payload).hexdigest()


def is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name == "VERSION"


def ignored(relative: Path) -> bool:
    return any(part in SKIP_PARTS for part in relative.parts) or (
        relative.suffix.lower() in SKIP_SUFFIXES
    )


def runtime_files(root: Path) -> list[Path]:
    files: list[Path] = []
    package = root / "datawork"
    if package.is_dir():
        files.extend(path for path in package.rglob("*") if path.is_file())
    files.extend(root / name for name in ROOT_FILES if (root / name).is_file())
    return sorted(
        (
            path
            for path in files
            if not ignored(path.relative_to(root))
        ),
        key=lambda item: item.relative_to(root).as_posix(),
    )


def runtime_map(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(
            path,
            normalize_text=is_text(path),
        )
        for path in runtime_files(root)
    }


def copy_runtime(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in runtime_files(source):
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def write_manifest(mapping: dict[str, str], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "".join(f"{digest}  {relative}\n" for relative, digest in sorted(mapping.items())),
        encoding="utf-8",
        newline="\n",
    )


def git_value(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout.strip()


def restart_service_function() -> str:
    return r'''
supervisor_controllers() {
  printf '%s\n' \
    "$(command -v supervisorctl 2>/dev/null || true)" \
    "/usr/bin/supervisorctl" "/usr/local/bin/supervisorctl" \
    "/www/server/panel/pyenv/bin/supervisorctl" \
    "/www/server/panel/plugin/supervisor/supervisorctl" | awk 'NF && !seen[$0]++'
}

restart_service() {
  local controller="" target_pid="" name="" state="" controller_pid=""
  target_pid="$(pgrep -fo "$APP_DIR/bt_start.py" 2>/dev/null || true)"
  while IFS= read -r controller; do
    [[ -x "$controller" ]] || continue
    if [[ -n "$SERVICE_NAME" ]] && "$controller" restart "$SERVICE_NAME"; then
      return 0
    fi
    [[ -n "$target_pid" ]] || continue
    while read -r name state _; do
      [[ "$state" == "RUNNING" ]] || continue
      controller_pid="$("$controller" pid "$name" 2>/dev/null || true)"
      if [[ "$controller_pid" == "$target_pid" ]] && "$controller" restart "$name"; then
        SERVICE_NAME="$name"
        return 0
      fi
    done < <("$controller" status 2>/dev/null || true)
  done < <(supervisor_controllers)
  if [[ -n "$SERVICE_NAME" ]] && command -v systemctl >/dev/null 2>&1 \
    && systemctl list-unit-files "$SERVICE_NAME.service" --no-legend 2>/dev/null \
      | grep -q "$SERVICE_NAME.service"; then
    systemctl restart "$SERVICE_NAME.service"
    return 0
  fi
  return 1
}
'''


def installer_script(delete_paths: list[str]) -> str:
    root_files = "\n".join(f'  "{item}"' for item in ROOT_FILES)
    accepted_versions = " ".join(ACCEPTED_BASELINE_VERSIONS)
    return f'''#!/usr/bin/env bash
set -Eeuo pipefail

umask 022
PATCH_ID="{PATCH_ID}"
TARGET_VERSION="{VERSION}"
DEFAULT_APP_DIR="/www/wwwroot/1490473838.cn/datework"
APP_DIR="${{DATAWORK_APP_DIR:-$DEFAULT_APP_DIR}}"
SERVICE_NAME="${{DATAWORK_SUPERVISOR_NAME:-}}"
PATCH_DIR="$(cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")" && pwd -P)"
PAYLOAD_DIR="$PATCH_DIR/payload"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_DIR="$BACKUP_ROOT/${{PATCH_ID}}_$(date +%Y%m%d_%H%M%S)"
BACKUP_MARKER="$APP_DIR/updates/.last_v15_pairing_hotfix_backup"
HEALTH_URL="http://127.0.0.1:8765/api/health"
OPENAPI_URL="http://127.0.0.1:8765/openapi.json"
ROOT_FILES=(
{root_files}
)
ACCEPTED_VERSIONS=({accepted_versions})

log() {{ printf '[DataWork V1.5 热补丁] %s\\n' "$*"; }}
fail() {{ printf '[DataWork V1.5 热补丁] 错误：%s\\n' "$*" >&2; exit 1; }}
normalized_sha() {{ tr -d '\\r' < "$1" | sha256sum | awk '{{print $1}}'; }}

manifest_matches() {{
  local manifest="$1" expected="" relative="" actual=""
  while read -r expected relative; do
    [[ -n "$expected" && -n "$relative" ]] || continue
    [[ -f "$APP_DIR/$relative" ]] || return 1
    actual="$(normalized_sha "$APP_DIR/$relative")"
    [[ "$actual" == "$expected" ]] || return 1
  done < "$manifest"
}}

known_delete_paths_absent() {{
  local relative=""
  while IFS= read -r relative; do
    [[ -n "$relative" ]] || continue
    [[ ! -e "$APP_DIR/$relative" ]] || return 1
  done < "$PATCH_DIR/DELETE_PATHS.txt"
}}

match_known_baseline() {{
  local manifest=""
  for manifest in "$PATCH_DIR"/BASELINES/*.sha256; do
    [[ -f "$manifest" ]] || continue
    if manifest_matches "$manifest"; then
      basename "$manifest" .sha256
      return 0
    fi
  done
  return 1
}}

{restart_service_function()}

[[ "$(id -u)" -eq 0 ]] || fail "请使用 root 用户运行。"
[[ "$APP_DIR" == "$DEFAULT_APP_DIR" || -n "${{DATAWORK_APP_DIR:-}}" ]] \
  || fail "目标路径异常：$APP_DIR"
[[ -d "$APP_DIR/datawork" && -f "$APP_DIR/VERSION" ]] \
  || fail "目标不是完整 DataWork 服务：$APP_DIR"
[[ -x "$APP_DIR/.venv/bin/python" ]] \
  || fail "未找到现有虚拟环境 Python：$APP_DIR/.venv/bin/python"
[[ -d "$APP_DIR/data" ]] || fail "缺少运行数据目录：$APP_DIR/data"
[[ -d "$PAYLOAD_DIR/datawork/web/static/assets" ]] \
  || fail "补丁 payload 不完整。"

log "校验热补丁自身 SHA-256……"
(cd "$PATCH_DIR" && sha256sum -c SHA256SUMS.txt)

CURRENT_VERSION="$(tr -d '[:space:]' < "$APP_DIR/VERSION")"
if manifest_matches "$PATCH_DIR/TARGET_SHA256.txt" \
  && known_delete_paths_absent \
  && [[ "$CURRENT_VERSION" == "$TARGET_VERSION" ]]; then
  log "服务器已经是本热补丁目标版本，无需重复安装。"
  exit 0
fi

VERSION_ALLOWED=0
for candidate in "${{ACCEPTED_VERSIONS[@]}}"; do
  [[ "$CURRENT_VERSION" == "$candidate" ]] && VERSION_ALLOWED=1
done
[[ "$VERSION_ALLOWED" -eq 1 ]] \
  || fail "服务器版本 $CURRENT_VERSION 不在本补丁支持范围（0.4.9 / 1.0.0）。"

BASELINE_NAME="$(match_known_baseline || true)"
if [[ -z "$BASELINE_NAME" ]]; then
  if [[ "${{DATAWORK_ALLOW_BASELINE_MISMATCH:-0}}" != "1" ]]; then
    fail "服务器程序文件与三套已审核基线均不一致。安装已停止，未覆盖任何文件。"
  fi
  BASELINE_NAME="explicitly-authorized-unknown"
  log "警告：已按显式授权跳过基线哈希保护。"
else
  log "识别服务器基线：$BASELINE_NAME"
fi

APP_OWNER="$(stat -c '%U' "$APP_DIR/datawork")"
APP_GROUP="$(stat -c '%G' "$APP_DIR/datawork")"
mkdir -p "$BACKUP_DIR/root"
log "完整备份当前程序到：$BACKUP_DIR"
cp -a "$APP_DIR/datawork" "$BACKUP_DIR/datawork"
: > "$BACKUP_DIR/root_files_present.txt"
for relative in "${{ROOT_FILES[@]}}"; do
  if [[ -f "$APP_DIR/$relative" ]]; then
    cp -a "$APP_DIR/$relative" "$BACKUP_DIR/root/$relative"
    printf '%s\\n' "$relative" >> "$BACKUP_DIR/root_files_present.txt"
  fi
done
printf '%s\\n' "$CURRENT_VERSION" > "$BACKUP_DIR/original_version.txt"
printf '%s\\n' "$BASELINE_NAME" > "$BACKUP_DIR/recognized_baseline.txt"
printf '%s\\n' "$BACKUP_DIR" > "$BACKUP_MARKER"
chmod 0600 "$BACKUP_MARKER"

log "覆盖 V1.5 运行源码；保留 .venv、data、updates、数据库和用户配置……"
while IFS= read -r -d '' source; do
  relative="${{source#$PAYLOAD_DIR/}}"
  install -D -m 0644 "$source" "$APP_DIR/$relative"
done < <(find "$PAYLOAD_DIR/datawork" -type f -print0)
for relative in "${{ROOT_FILES[@]}}"; do
  [[ -f "$PAYLOAD_DIR/$relative" ]] || continue
  install -m 0644 "$PAYLOAD_DIR/$relative" "$APP_DIR/$relative"
done
while IFS= read -r relative; do
  [[ -n "$relative" ]] || continue
  [[ "$relative" == datawork/* && "$relative" != *'..'* ]] \
    || fail "删除清单包含非法路径：$relative"
  rm -f -- "$APP_DIR/$relative"
done < "$PATCH_DIR/DELETE_PATHS.txt"
find "$APP_DIR/datawork" -type d -name __pycache__ -prune -exec rm -rf -- {{}} +
chown -R "$APP_OWNER:$APP_GROUP" "$APP_DIR/datawork"
for relative in "${{ROOT_FILES[@]}}"; do
  [[ -e "$APP_DIR/$relative" ]] && chown "$APP_OWNER:$APP_GROUP" "$APP_DIR/$relative"
done

manifest_matches "$PATCH_DIR/TARGET_SHA256.txt" \
  || fail "覆盖后目标文件哈希不一致；请立即运行 ./回滚本次热补丁.sh。"
known_delete_paths_absent \
  || fail "旧运行文件未清理干净；请立即运行 ./回滚本次热补丁.sh。"

log "使用现有虚拟环境执行 V1.5 离线功能烟雾测试……"
(
  cd "$APP_DIR"
  PYTHONDONTWRITEBYTECODE=1 DATAWORK_HOME="$APP_DIR/data" \
    "$APP_DIR/.venv/bin/python" - <<'PY'
import pandas as pd
import datawork
from datawork.application.analysis_service import AnalysisService
from datawork.application.preflight_service import PreflightService
from datawork.core.method_registry import list_methods
from datawork.core.plan import AnalysisPlan

assert datawork.__version__ == "1.5.0"
frame = pd.DataFrame([
    {{"year": 2025, "variety": "V1", "mode": "M1", "spray": "T1", "value": 20.0}},
    {{"year": 2025, "variety": "V1", "mode": "M1", "spray": "CK1", "value": 10.0}},
    {{"year": 2025, "variety": "V1", "mode": "M1", "spray": "T1", "value": 22.0}},
    {{"year": 2025, "variety": "V1", "mode": "M1", "spray": "CK1", "value": 11.0}},
    {{"year": 2025, "variety": "V1", "mode": "M1", "spray": "T1", "value": 24.0}},
    {{"year": 2025, "variety": "V1", "mode": "M1", "spray": "CK1", "value": 12.0}},
])
plan = AnalysisPlan.model_validate({{
    "interface_mode": "professional",
    "method": "one_sample_ttest",
    "dependent_variables": ["NDR"],
    "pairing": {{
        "group_column": "spray",
        "mappings": [{{"treatment": "T1", "control": "CK1"}}],
        "match_columns": ["year", "variety", "mode"],
        "pair_id_column": None,
        "derived_columns": [
            {{
                "id": "ndr",
                "name": "NDR",
                "source_column": "value",
                "formula": "[对照值]",
                "unit": "百分点",
                "decimal_places": 8,
            }}
        ],
    }},
}})
prepared, logs, warnings = AnalysisService.prepare_frame(frame, plan)
assert prepared["NDR"].tolist() == [10.0, 11.0, 12.0]
assert not warnings
audit = next(item for item in logs if item["operation"] == "pairing")
assert audit["successful_pairs"] == 3
report = PreflightService().inspect(frame, plan.model_dump(mode="json"))
assert report.ready
assert report.pairing_summary["successful_pairs"] == 3
AnalysisService().execute(frame, plan)
assert len(list_methods(runnable_only=True)) == 47
print("offline_v15_smoke=passed")
PY
)

if ! restart_service; then
  log "文件、哈希和离线测试均已完成，但未识别到进程守护名称。"
  log "请在宝塔进程守护管理器中手动重启 DataWork，再执行："
  log "curl -fsS $HEALTH_URL"
  exit 2
fi

log "等待 V1.5 服务恢复……"
for _ in $(seq 1 30); do
  if health_json="$(curl -fsS "$HEALTH_URL" 2>/dev/null)" \
    && printf '%s' "$health_json" | "$APP_DIR/.venv/bin/python" -c \
      'import json,sys; p=json.load(sys.stdin); assert p["status"]=="ok"; assert p["version"]=="1.5.0"; assert p["features"]["pairing_workflow"] is True; assert p["features"]["dependent_variable_groups"] is True' \
    && curl -fsS "$OPENAPI_URL" | grep -q '/api/preflight'; then
    log "更新成功：服务版本、V1.5 能力和预检接口均已加载。"
    log "备份位置：$BACKUP_DIR"
    exit 0
  fi
  sleep 1
done
fail "服务未在 30 秒内通过 V1.5 健康检查；请查看进程日志，必要时运行 ./回滚本次热补丁.sh。"
'''


def rollback_script() -> str:
    root_files = "\n".join(f'  "{item}"' for item in ROOT_FILES)
    return f'''#!/usr/bin/env bash
set -Eeuo pipefail

DEFAULT_APP_DIR="/www/wwwroot/1490473838.cn/datework"
APP_DIR="${{DATAWORK_APP_DIR:-$DEFAULT_APP_DIR}}"
SERVICE_NAME="${{DATAWORK_SUPERVISOR_NAME:-}}"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_MARKER="$APP_DIR/updates/.last_v15_pairing_hotfix_backup"
HEALTH_URL="http://127.0.0.1:8765/api/health"
ROOT_FILES=(
{root_files}
)

log() {{ printf '[DataWork V1.5 热补丁回滚] %s\\n' "$*"; }}
fail() {{ printf '[DataWork V1.5 热补丁回滚] 错误：%s\\n' "$*" >&2; exit 1; }}

{restart_service_function()}

[[ "$(id -u)" -eq 0 ]] || fail "请使用 root 用户运行。"
[[ "$APP_DIR" == "$DEFAULT_APP_DIR" || -n "${{DATAWORK_APP_DIR:-}}" ]] \
  || fail "目标路径异常：$APP_DIR"
[[ -f "$BACKUP_MARKER" ]] || fail "没有找到本次热补丁的备份标记。"
BACKUP_DIR="$(tr -d '\\r\\n' < "$BACKUP_MARKER")"
case "$BACKUP_DIR" in
  "$BACKUP_ROOT"/*) ;;
  *) fail "备份路径不在允许目录内：$BACKUP_DIR" ;;
esac
[[ -d "$BACKUP_DIR/datawork" && -f "$BACKUP_DIR/root_files_present.txt" ]] \
  || fail "备份不完整：$BACKUP_DIR"

APP_OWNER="$(stat -c '%U' "$APP_DIR/datawork")"
APP_GROUP="$(stat -c '%G' "$APP_DIR/datawork")"
log "恢复完整程序备份：$BACKUP_DIR"
rm -rf -- "$APP_DIR/datawork"
cp -a "$BACKUP_DIR/datawork" "$APP_DIR/datawork"
for relative in "${{ROOT_FILES[@]}}"; do
  if grep -Fxq "$relative" "$BACKUP_DIR/root_files_present.txt"; then
    cp -a "$BACKUP_DIR/root/$relative" "$APP_DIR/$relative"
  else
    rm -f -- "$APP_DIR/$relative"
  fi
done
chown -R "$APP_OWNER:$APP_GROUP" "$APP_DIR/datawork"
for relative in "${{ROOT_FILES[@]}}"; do
  [[ -e "$APP_DIR/$relative" ]] && chown "$APP_OWNER:$APP_GROUP" "$APP_DIR/$relative"
done
rm -f -- "$BACKUP_MARKER"

if ! restart_service; then
  log "程序文件已恢复，但未识别到进程守护名称。"
  log "请在宝塔进程守护管理器中手动重启 DataWork。"
  exit 2
fi
for _ in $(seq 1 30); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    log "回滚完成，服务已恢复。保留备份目录供审计：$BACKUP_DIR"
    exit 0
  fi
  sleep 1
done
fail "文件已恢复，但服务未在 30 秒内通过健康检查。"
'''


def instructions() -> str:
    return f"""DataWork {VERSION} 配对映射与联合因变量服务器热补丁
========================================================

目标路径：/www/wwwroot/1490473838.cn/datework
支持基线：
1. 原始 DataWork 0.4.9 服务器源码；
2. 已安装“自定义列与拆分继承”旧热补丁的 0.4.9；
3. DataWork 1.0.0 网站部署版本。

主要更新：
- 专业模式处理—对照一一配对、匹配标签和原始顺序/显式 ID 配对；
- 最多 10 个配对计算列、基础四则运算、括号和 0–8 位小数；
- 配对列只能作为因变量，普通自定义列保持单向无环依赖；
- 联合因变量分组、因素模型和拆分维度统一展开任务；
- 分层执行审核与旧后端能力守卫；
- MANOVA 按交互分支完整比较；
- V1.5 Vue 生产前端和版本 1.5.0。

安全边界：
- 复用服务器现有 .venv，不下载 Python、不执行 pip install；
- 不读取或覆盖 data/、数据库、上传文件、报告、工作区密码、AI 密钥；
- 安装前验证 ZIP/包内 SHA-256，并匹配三套已审核基线之一；
- 不匹配时立即停止，除非管理员审核后显式设置覆盖开关；
- 覆盖前完整备份 datawork 目录和根版本文件；
- 支持一条命令回滚。

上传和安装：
1. 将以下两个文件上传到 /www/wwwroot/1490473838.cn/datework/updates/：
   - {PACKAGE_NAME}.zip
   - {PACKAGE_NAME}.zip.sha256

2. 服务器执行：

   cd /www/wwwroot/1490473838.cn/datework/updates
   sha256sum -c {PACKAGE_NAME}.zip.sha256
   unzip {PACKAGE_NAME}.zip
   cd {PACKAGE_NAME}
   chmod +x 应用热补丁.sh 回滚本次热补丁.sh
   ./应用热补丁.sh

3. 若脚本返回代码 2，表示文件和离线测试已完成，但没有自动识别宝塔进程守护名称。
   请在宝塔面板手动重启 DataWork，然后验证：

   curl -fsS http://127.0.0.1:8765/api/health

   正常结果应包含 version=1.5.0，以及 pairing_workflow=true、
   dependent_variable_groups=true。

回滚：

   cd /www/wwwroot/1490473838.cn/datework/updates/{PACKAGE_NAME}
   ./回滚本次热补丁.sh

只有在确认服务器代码曾被人工修改、并已人工审核差异后，才允许：

   DATAWORK_ALLOW_BASELINE_MISMATCH=1 ./应用热补丁.sh
"""


def write_sha_manifest(root: Path) -> None:
    lines = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            lines.append(f"{sha256(path)}  {path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_zip(package: Path) -> Path:
    archive_path = package.parent / f"{package.name}.zip"
    checksum_path = package.parent / f"{archive_path.name}.sha256"
    for path in (archive_path, checksum_path):
        if path.exists():
            path.unlink()
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(
            package.rglob("*"),
            key=lambda item: item.relative_to(package).as_posix(),
        ):
            if not path.is_file():
                continue
            relative = Path(package.name) / path.relative_to(package)
            info = zipfile.ZipInfo(relative.as_posix())
            info.create_system = 3
            mode = 0o755 if path.suffix == ".sh" else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    checksum_path.write_text(
        f"{sha256(archive_path)}  {archive_path.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    return archive_path


def apply_payload(stage: Path, payload: Path, delete_paths: list[str]) -> None:
    copy_runtime(payload, stage)
    for relative in delete_paths:
        target = stage / relative
        if target.is_file():
            target.unlink()


def verify_simulated_apply(
    baselines: list[tuple[str, Path, dict[str, str]]],
    payload: Path,
    target_map: dict[str, str],
    delete_paths: list[str],
) -> list[dict[str, object]]:
    verify_root = Path(
        tempfile.mkdtemp(prefix=".v15-hotfix-verify-", dir=ROOT.parent)
    )
    results: list[dict[str, object]] = []
    try:
        for name, baseline, baseline_map in baselines:
            stage = verify_root / name / "app"
            backup = verify_root / name / "backup"
            copy_runtime(baseline, stage)
            copy_runtime(stage, backup)
            apply_payload(stage, payload, delete_paths)
            actual_target = runtime_map(stage)
            if actual_target != target_map:
                missing = sorted(target_map.keys() - actual_target.keys())
                extra = sorted(actual_target.keys() - target_map.keys())
                changed = sorted(
                    key
                    for key in target_map.keys() & actual_target.keys()
                    if target_map[key] != actual_target[key]
                )
                raise RuntimeError(
                    f"{name} 模拟应用不一致：missing={missing}, extra={extra}, changed={changed}"
                )
            shutil.rmtree(stage)
            copy_runtime(backup, stage)
            if runtime_map(stage) != baseline_map:
                raise RuntimeError(f"{name} 模拟回滚未恢复原始基线")
            results.append(
                {
                    "baseline": name,
                    "apply": "passed",
                    "rollback": "passed",
                    "baseline_files": len(baseline_map),
                    "target_files": len(target_map),
                }
            )
    finally:
        shutil.rmtree(verify_root, ignore_errors=True)
    return results


def verify_package(package: Path, archive: Path) -> dict[str, object]:
    manifest = package / "SHA256SUMS.txt"
    checked = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        target = package / relative
        if not target.is_file() or sha256(target) != expected:
            raise RuntimeError(f"包内 SHA-256 校验失败：{relative}")
        checked += 1
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        expected_prefix = f"{package.name}/"
        if not names or any(not name.startswith(expected_prefix) for name in names):
            raise RuntimeError("ZIP 根目录结构异常")
        shell_modes = {
            Path(name).name: (zipped.getinfo(name).external_attr >> 16) & 0o777
            for name in names
            if name.endswith(".sh")
        }
        if not shell_modes or any(mode != 0o755 for mode in shell_modes.values()):
            raise RuntimeError(f"ZIP Shell 执行权限异常：{shell_modes}")
    return {
        "sha256_entries": checked,
        "zip_entries": len(names),
        "zip_sha256": sha256(archive),
        "shell_modes": shell_modes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 DataWork V1.5 多基线服务器热补丁")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    release_root = (ROOT / "发布包").resolve()
    if release_root not in output.parents:
        raise SystemExit(f"输出目录必须位于发布包目录：{release_root}")
    if VERSION != "1.5.0":
        raise SystemExit(f"当前源码版本必须是 1.5.0，实际为：{VERSION}")
    if not (ROOT / "datawork" / "core" / "pairing.py").is_file():
        raise SystemExit("当前源码缺少 V1.5 配对核心")

    baselines: list[tuple[str, Path, dict[str, str]]] = []
    for name, path in BASELINES:
        resolved = path.resolve()
        if not (resolved / "datawork" / "core" / "plan.py").is_file():
            raise SystemExit(f"服务器基线不完整：{name} -> {resolved}")
        baselines.append((name, resolved, runtime_map(resolved)))

    if output.exists():
        shutil.rmtree(output)
    payload = output / "payload"
    copy_runtime(ROOT, payload)
    target_map = runtime_map(ROOT)
    write_manifest(target_map, output / "TARGET_SHA256.txt")
    for name, _path, mapping in baselines:
        write_manifest(mapping, output / "BASELINES" / f"{name}.sha256")

    baseline_keys = set().union(*(mapping.keys() for _, _, mapping in baselines))
    delete_paths = sorted(baseline_keys - target_map.keys())
    expected_delete_names = {
        "datawork/ui.py",
        "datawork/web/static/assets/index-CPsr4TFv.js",
        "datawork/web/static/assets/index-mCJiNXhg.css",
        "datawork/web/static/assets/index-BkO9JSkG.css",
        "datawork/web/static/assets/index-DALge41P.js",
        "datawork/web/static/assets/index-C9-Qod4X.js",
    }
    if set(delete_paths) != expected_delete_names:
        raise RuntimeError(f"删除集合超出已审核范围：{delete_paths}")
    (output / "DELETE_PATHS.txt").write_text(
        "\n".join(delete_paths) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    baseline_diffs = {}
    for name, path, mapping in baselines:
        baseline_diffs[name] = {
            "path": str(path),
            "version": (path / "VERSION").read_text(encoding="utf-8").strip(),
            "added": sorted(target_map.keys() - mapping.keys()),
            "modified": sorted(
                key
                for key in target_map.keys() & mapping.keys()
                if target_map[key] != mapping[key]
            ),
            "deleted": sorted(mapping.keys() - target_map.keys()),
        }

    simulation = verify_simulated_apply(
        baselines,
        payload,
        target_map,
        delete_paths,
    )
    source_status = git_value("status", "--porcelain")
    patch_info = {
        "patch_id": PATCH_ID,
        "version": VERSION,
        "package_name": PACKAGE_NAME,
        "created_date": "2026-07-23",
        "site_root": "/www/wwwroot/1490473838.cn",
        "app_dir": "/www/wwwroot/1490473838.cn/datework",
        "accepted_versions": list(ACCEPTED_BASELINE_VERSIONS),
        "source_branch": git_value("branch", "--show-current"),
        "source_commit": git_value("rev-parse", "HEAD"),
        "source_has_uncommitted_changes": bool(source_status),
        "source_state_note": "validated V1.5 working tree; package integrity is locked by TARGET_SHA256.txt and SHA256SUMS.txt",
        "baseline_diffs": baseline_diffs,
        "delete_paths": delete_paths,
        "excluded": [
            ".venv/",
            "data/",
            "updates/",
            "*.sqlite3",
            "*.db",
            "API keys",
            "password hashes",
            "reports",
            "uploads",
        ],
        "python_runtime_action": "reuse existing .venv; no Python download; no pip install",
        "simulated_apply_and_rollback": simulation,
    }
    (output / "PATCH_INFO.json").write_text(
        json.dumps(patch_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output / "应用热补丁.sh").write_text(
        installer_script(delete_paths),
        encoding="utf-8",
        newline="\n",
    )
    (output / "回滚本次热补丁.sh").write_text(
        rollback_script(),
        encoding="utf-8",
        newline="\n",
    )
    (output / "热补丁说明.txt").write_text(
        instructions(),
        encoding="utf-8",
        newline="\n",
    )
    (output / "PACKAGE_VERIFICATION.json").write_text(
        json.dumps(
            {
                "simulated_apply_and_rollback": simulation,
                "target_runtime_files": len(target_map),
                "reviewed_delete_paths": len(delete_paths),
                "status": "generated; SHA256SUMS and ZIP are verified before delivery",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_sha_manifest(output)
    archive = build_zip(output)
    package_verification = verify_package(output, archive)

    print(f"热补丁目录：{output}")
    print(f"热补丁 ZIP：{archive}")
    print(f"ZIP SHA-256：{package_verification['zip_sha256']}")
    print(
        "基线模拟："
        + "；".join(
            f"{item['baseline']} 应用/回滚通过"
            for item in simulation
        )
    )
    print(
        f"目标运行文件={len(target_map)}，删除旧文件={len(delete_paths)}，"
        f"包内校验项={package_verification['sha256_entries']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
