#!/usr/bin/env python3
"""Build the verified DataWork 0.4.9 derived-column server hotfix."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
PATCH_ID = "datawork_0.4.9_derived_split_20260723"
DEFAULT_BASELINE = ROOT / "web主页本地部分" / "datawork"
DEFAULT_LATEST = ROOT.parent / "DataWork-Web-inspect" / "DataWork服务"
DEFAULT_OUTPUT = ROOT / "发布包" / "DataWork-v0.4.9-自定义列与拆分继承-服务器热补丁-20260723"

ROOT_FILES = (
    "README.md",
    "VERSION",
    "bt_start.py",
    "pyproject.toml",
    "requirements.txt",
    "宝塔面板部署说明.txt",
    "服务器环境准备.sh",
    "configure_server_ai.py",
    "设置工作区密码.sh",
    "设置服务器AI配置.sh",
)
BASELINE_GUARDS = (
    "datawork/application/analysis_service.py",
    "datawork/application/preflight_service.py",
    "datawork/core/formula.py",
    "datawork/core/plan.py",
    "datawork/core/splitting.py",
    "datawork/core/validation.py",
    "datawork/web/app.py",
    "datawork/web/schemas.py",
    "datawork/web/static/index.html",
    "datawork/web/static/assets/index-CPsr4TFv.js",
    "datawork/web/static/assets/index-mCJiNXhg.css",
)
TARGET_GUARDS = (
    "datawork/application/analysis_service.py",
    "datawork/core/formula.py",
    "datawork/core/plan.py",
    "datawork/core/splitting.py",
    "datawork/web/app.py",
    "datawork/web/static/index.html",
    "datawork/web/static/assets/index-BkO9JSkG.css",
    "datawork/web/static/assets/index-DALge41P.js",
)
DELETE_PATHS = (
    "datawork/ui.py",
    "datawork/web/static/assets/index-CPsr4TFv.js",
    "datawork/web/static/assets/index-mCJiNXhg.css",
)
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", "data"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".db", ".sqlite3"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".json", ".sh", ".html", ".css", ".js", ".j2"}


def sha256(path: Path, *, normalize_text: bool = False) -> str:
    payload = path.read_bytes()
    if normalize_text:
        # Keep file contents exact while making Windows/Linux line endings
        # comparable.  The server-side checker performs the same CR removal.
        payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"")
    return hashlib.sha256(payload).hexdigest()


def is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name == "VERSION"


def copy_runtime_tree(source: Path, destination: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {
            name for name in names
            if name in SKIP_PARTS or Path(name).suffix.lower() in SKIP_SUFFIXES
        }

    shutil.copytree(source, destination, ignore=ignore)


def runtime_map(root: Path) -> dict[str, str]:
    files: list[Path] = []
    package = root / "datawork"
    if package.is_dir():
        files.extend(path for path in package.rglob("*") if path.is_file())
    files.extend(root / name for name in ROOT_FILES if (root / name).is_file())
    result: dict[str, str] = {}
    for path in files:
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        result[relative.as_posix()] = sha256(path, normalize_text=is_text(path))
    return result


def write_normalized_manifest(root: Path, relative_paths: tuple[str, ...], target: Path) -> None:
    lines = []
    for relative in relative_paths:
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"基线/目标缺少保护文件：{path}")
        lines.append(f"{sha256(path, normalize_text=True)}  {relative}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def installer_script() -> str:
    root_files = "\n".join(f'  "{item}"' for item in ROOT_FILES)
    return f'''#!/usr/bin/env bash
set -Eeuo pipefail

umask 022
PATCH_ID="{PATCH_ID}"
DEFAULT_SITE_ROOT="/www/wwwroot/1490473838.cn"
DEFAULT_APP_DIR="$DEFAULT_SITE_ROOT/datework"
APP_DIR="${{DATAWORK_APP_DIR:-$DEFAULT_APP_DIR}}"
SERVICE_NAME="${{DATAWORK_SUPERVISOR_NAME:-}}"
PATCH_DIR="$(cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")" && pwd -P)"
PAYLOAD_DIR="$PATCH_DIR/payload"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_DIR="$BACKUP_ROOT/${{PATCH_ID}}_$(date +%Y%m%d_%H%M%S)"
BACKUP_MARKER="$APP_DIR/updates/.last_derived_split_hotfix_backup"
HEALTH_URL="http://127.0.0.1:8765/api/health"
OPENAPI_URL="http://127.0.0.1:8765/openapi.json"
ROOT_FILES=(
{root_files}
)

log() {{ printf '[DataWork 自定义列热补丁] %s\n' "$*"; }}
fail() {{ printf '[DataWork 自定义列热补丁] 错误：%s\n' "$*" >&2; exit 1; }}
normalized_sha() {{ tr -d '\\r' < "$1" | sha256sum | awk '{{print $1}}'; }}

manifest_matches() {{
  local manifest="$1" relative expected actual
  while IFS='  ' read -r expected relative; do
    [[ -n "$expected" && -n "$relative" ]] || continue
    [[ -f "$APP_DIR/$relative" ]] || return 1
    actual="$(normalized_sha "$APP_DIR/$relative")"
    [[ "$actual" == "$expected" ]] || return 1
  done < "$manifest"
}}

supervisor_controllers() {{
  printf '%s\n' \
    "$(command -v supervisorctl 2>/dev/null || true)" \
    "/usr/bin/supervisorctl" "/usr/local/bin/supervisorctl" \
    "/www/server/panel/pyenv/bin/supervisorctl" \
    "/www/server/panel/plugin/supervisor/supervisorctl" | awk 'NF && !seen[$0]++'
}}

restart_service() {{
  local controller="" target_pid="" name="" state="" controller_pid=""
  target_pid="$(pgrep -fo "$APP_DIR/bt_start.py" 2>/dev/null || true)"
  while IFS= read -r controller; do
    [[ -x "$controller" ]] || continue
    if [[ -n "$SERVICE_NAME" ]] && "$controller" restart "$SERVICE_NAME"; then return 0; fi
    [[ -n "$target_pid" ]] || continue
    while read -r name state _; do
      [[ "$state" == "RUNNING" ]] || continue
      controller_pid="$($controller pid "$name" 2>/dev/null || true)"
      if [[ "$controller_pid" == "$target_pid" ]] && "$controller" restart "$name"; then
        SERVICE_NAME="$name"; return 0
      fi
    done < <("$controller" status 2>/dev/null || true)
  done < <(supervisor_controllers)
  if [[ -n "$SERVICE_NAME" ]] && command -v systemctl >/dev/null 2>&1 \
    && systemctl list-unit-files "$SERVICE_NAME.service" --no-legend 2>/dev/null | grep -q "$SERVICE_NAME.service"; then
    systemctl restart "$SERVICE_NAME.service"; return 0
  fi
  return 1
}}

[[ "$(id -u)" -eq 0 ]] || fail "请使用 root 用户运行。"
[[ "$APP_DIR" == "/www/wwwroot/1490473838.cn/datework" || -n "${{DATAWORK_APP_DIR:-}}" ]] \
  || fail "目标路径异常：$APP_DIR"
[[ -d "$APP_DIR/datawork" && -f "$APP_DIR/VERSION" ]] || fail "目标不是完整 DataWork 服务：$APP_DIR"
[[ "$(tr -d '[:space:]' < "$APP_DIR/VERSION")" == "{VERSION}" ]] || fail "本补丁仅适用于 DataWork {VERSION}。"
[[ -x "$APP_DIR/.venv/bin/python" ]] || fail "未找到现有虚拟环境 Python：$APP_DIR/.venv/bin/python"
[[ -d "$APP_DIR/data" ]] || fail "缺少运行数据目录：$APP_DIR/data"
[[ -d "$PAYLOAD_DIR/datawork/web/static/assets" ]] || fail "补丁 payload 不完整。"

log "校验补丁自身 SHA-256……"
(cd "$PATCH_DIR" && sha256sum -c SHA256SUMS.txt)

if manifest_matches "$PATCH_DIR/TARGET_GUARDS_SHA256.txt" \
  && [[ ! -e "$APP_DIR/datawork/ui.py" ]] \
  && [[ ! -e "$APP_DIR/datawork/web/static/assets/index-CPsr4TFv.js" ]] \
  && [[ ! -e "$APP_DIR/datawork/web/static/assets/index-mCJiNXhg.css" ]]; then
  log "目标已经是本热补丁版本，无需重复安装。"
  exit 0
fi

if ! manifest_matches "$PATCH_DIR/BASELINE_GUARDS_SHA256.txt"; then
  if [[ "${{DATAWORK_ALLOW_BASELINE_MISMATCH:-0}}" != "1" ]]; then
    fail "服务器程序文件与已审核基线不一致。为防止覆盖未知修改，安装已停止；如已人工核对，可设置 DATAWORK_ALLOW_BASELINE_MISMATCH=1 后重试。"
  fi
  log "警告：已按显式授权跳过基线不一致保护。"
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
    printf '%s\n' "$relative" >> "$BACKUP_DIR/root_files_present.txt"
  fi
done
printf '%s\n' "$BACKUP_DIR" > "$BACKUP_MARKER"
chmod 0600 "$BACKUP_MARKER"

log "覆盖最新运行源码；保留 .venv、data、updates 和全部用户数据……"
while IFS= read -r -d '' source; do
  relative="${{source#$PAYLOAD_DIR/}}"
  install -D -m 0644 "$source" "$APP_DIR/$relative"
done < <(find "$PAYLOAD_DIR/datawork" -type f -print0)
for relative in "${{ROOT_FILES[@]}}"; do
  [[ -f "$PAYLOAD_DIR/$relative" ]] || continue
  mode=0644; [[ "$relative" == *.sh ]] && mode=0755
  install -m "$mode" "$PAYLOAD_DIR/$relative" "$APP_DIR/$relative"
done
while IFS= read -r relative; do
  [[ "$relative" == datawork/* && "$relative" != *'..'* ]] || fail "删除清单包含非法路径：$relative"
  rm -f -- "$APP_DIR/$relative"
done < "$PATCH_DIR/DELETE_PATHS.txt"
find "$APP_DIR/datawork" -type d -name __pycache__ -prune -exec rm -rf -- {{}} +
chown -R "$APP_OWNER:$APP_GROUP" "$APP_DIR/datawork"
for relative in "${{ROOT_FILES[@]}}"; do
  [[ -e "$APP_DIR/$relative" ]] && chown "$APP_OWNER:$APP_GROUP" "$APP_DIR/$relative"
done

log "使用现有虚拟环境执行离线功能烟雾测试……"
(
  cd "$APP_DIR"
  PYTHONDONTWRITEBYTECODE=1 DATAWORK_HOME="$APP_DIR/data" "$APP_DIR/.venv/bin/python" - <<'PY'
import pandas as pd
from datawork.application.analysis_service import AnalysisService
from datawork.core.method_registry import list_methods
from datawork.core.plan import AnalysisPlan

frame = pd.DataFrame({{"x": [1.0, 2.0, 3.0], "z": ["A", "A", "B"]}})
plan = AnalysisPlan(
    interface_mode="professional", method="one_sample_ttest",
    dependent_variables=["custom"], split_by=["z"],
    derived_columns=[{{"name": "custom", "formula": "[x] / 3", "source_columns": ["x"]}}],
)
prepared, logs, warnings = AnalysisService.prepare_frame(frame, plan)
assert prepared["custom"].tolist() == [0.33333333, 0.66666667, 1.0]
assert logs[0]["decimal_places"] == 8 and not warnings
assert len(list_methods(runnable_only=True)) == 47
print("offline_smoke=passed")
PY
)

if ! restart_service; then
  log "文件和离线测试均已完成，但未识别到进程守护名称。"
  log "请在宝塔进程守护管理器中手动重启 DataWork，然后执行：curl -fsS $HEALTH_URL"
  exit 2
fi

log "等待服务恢复……"
for _ in $(seq 1 30); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1 \
    && curl -fsS "$OPENAPI_URL" | grep -q 'derived-preview'; then
    log "更新成功：服务健康，且自定义列预览接口已加载。"
    log "备份位置：$BACKUP_DIR"
    exit 0
  fi
  sleep 1
done
fail "服务未在 30 秒内通过健康检查。请查看进程日志，必要时运行 ./回滚本次热补丁.sh。"
'''


def rollback_script() -> str:
    root_files = "\n".join(f'  "{item}"' for item in ROOT_FILES)
    return f'''#!/usr/bin/env bash
set -Eeuo pipefail

PATCH_ID="{PATCH_ID}"
DEFAULT_APP_DIR="/www/wwwroot/1490473838.cn/datework"
APP_DIR="${{DATAWORK_APP_DIR:-$DEFAULT_APP_DIR}}"
SERVICE_NAME="${{DATAWORK_SUPERVISOR_NAME:-}}"
BACKUP_MARKER="$APP_DIR/updates/.last_derived_split_hotfix_backup"
HEALTH_URL="http://127.0.0.1:8765/api/health"
ROOT_FILES=(
{root_files}
)

log() {{ printf '[DataWork 自定义列热补丁回滚] %s\n' "$*"; }}
fail() {{ printf '[DataWork 自定义列热补丁回滚] 错误：%s\n' "$*" >&2; exit 1; }}

restart_service() {{
  local controller="" target_pid="" name="" state="" controller_pid=""
  target_pid="$(pgrep -fo "$APP_DIR/bt_start.py" 2>/dev/null || true)"
  for controller in "$(command -v supervisorctl 2>/dev/null || true)" /usr/bin/supervisorctl /usr/local/bin/supervisorctl /www/server/panel/pyenv/bin/supervisorctl /www/server/panel/plugin/supervisor/supervisorctl; do
    [[ -n "$controller" && -x "$controller" ]] || continue
    if [[ -n "$SERVICE_NAME" ]] && "$controller" restart "$SERVICE_NAME"; then return 0; fi
    while read -r name state _; do
      [[ "$state" == "RUNNING" ]] || continue
      controller_pid="$($controller pid "$name" 2>/dev/null || true)"
      if [[ -n "$target_pid" && "$controller_pid" == "$target_pid" ]] && "$controller" restart "$name"; then return 0; fi
    done < <("$controller" status 2>/dev/null || true)
  done
  return 1
}}

[[ "$(id -u)" -eq 0 ]] || fail "请使用 root 用户运行。"
[[ -f "$BACKUP_MARKER" ]] || fail "未找到最近一次补丁备份记录：$BACKUP_MARKER"
BACKUP_DIR="$(head -n 1 "$BACKUP_MARKER")"
EXPECTED_PREFIX="$APP_DIR/updates/backups/${{PATCH_ID}}_"
[[ "$BACKUP_DIR" == "$EXPECTED_PREFIX"* && -d "$BACKUP_DIR/datawork" ]] || fail "备份路径无效：$BACKUP_DIR"

APP_OWNER="$(stat -c '%U' "$APP_DIR/datawork")"
APP_GROUP="$(stat -c '%G' "$APP_DIR/datawork")"
FAILED_DIR="$APP_DIR/updates/failed_${{PATCH_ID}}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$FAILED_DIR/root"
log "保留当前失败版本到：$FAILED_DIR"
mv "$APP_DIR/datawork" "$FAILED_DIR/datawork"
cp -a "$BACKUP_DIR/datawork" "$APP_DIR/datawork"

for relative in "${{ROOT_FILES[@]}}"; do
  if grep -Fxq "$relative" "$BACKUP_DIR/root_files_present.txt"; then
    [[ -f "$APP_DIR/$relative" ]] && cp -a "$APP_DIR/$relative" "$FAILED_DIR/root/$relative"
    cp -a "$BACKUP_DIR/root/$relative" "$APP_DIR/$relative"
  elif [[ -e "$APP_DIR/$relative" ]]; then
    mv "$APP_DIR/$relative" "$FAILED_DIR/root/$relative"
  fi
done
chown -R "$APP_OWNER:$APP_GROUP" "$APP_DIR/datawork"

if restart_service; then
  for _ in $(seq 1 30); do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
      log "回滚成功，服务健康检查正常。"
      exit 0
    fi
    sleep 1
  done
  fail "文件已恢复，但服务未通过健康检查。"
fi
log "文件已恢复，请在宝塔进程守护管理器中手动重启 DataWork。"
exit 2
'''


def instructions() -> str:
    return f"""DataWork {VERSION} 自定义列与拆分继承服务器热补丁
====================================================

适用路径：/www/wwwroot/1490473838.cn/datework
主页根目录：/www/wwwroot/1490473838.cn
来源 Web 提交：a94140932ea65f9ba6877ff9dab708101369aa6f

本补丁包含：
1. 自定义列最多 10 个、每列最多引用 10 个原始数值列；
2. 基础算术与括号、实际 8 位小数；
3. 自定义列只能作为因变量，并继承来源列及全局拆分；
4. 空组合跳过、任务数量保护、旧方案自动整理；
5. 最新 Vue 静态前端；
6. 删除旧 Streamlit UI 和旧哈希静态资源。

安全边界：
- 使用服务器现有 .venv/bin/python，不下载或重建 Python；
- 不执行 pip install，本功能没有新增 Python 运行依赖；
- 不读取、覆盖或打包 data/、数据库、上传文件、报告、密码或 AI 密钥；
- 安装前校验补丁 SHA-256 和服务器旧基线；
- 安装前完整备份当前 datawork 程序目录及被覆盖的根文件。

上传与执行：
1. 将 ZIP 上传到 /www/wwwroot/1490473838.cn/datework/updates/。
2. 登录服务器后执行：

   cd /www/wwwroot/1490473838.cn/datework/updates
   unzip DataWork-v0.4.9-自定义列与拆分继承-服务器热补丁-20260723.zip
   cd DataWork-v0.4.9-自定义列与拆分继承-服务器热补丁-20260723
   chmod +x 应用热补丁.sh 回滚本次热补丁.sh
   sudo ./应用热补丁.sh

3. 若脚本提示无法自动识别 Supervisor 名称，请在宝塔进程守护管理器中手动重启 DataWork。
4. 手动验证：

   curl -fsS http://127.0.0.1:8765/api/health
   curl -fsS http://127.0.0.1:8765/openapi.json | grep derived-preview

回滚：sudo ./回滚本次热补丁.sh

如服务器代码曾被人工修改，基线保护会停止安装。只有完成差异审核后，才能显式使用：
DATAWORK_ALLOW_BASELINE_MISMATCH=1 sudo -E ./应用热补丁.sh
"""


def write_sha_manifest(root: Path) -> None:
    lines = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            lines.append(f"{sha256(path)}  {path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def build_zip(package: Path) -> Path:
    # ``Path.with_suffix`` truncates names such as ``DataWork-v0.4.9-...`` at
    # ``.4``.  Append the suffix so the release name remains intact.
    archive_path = package.parent / f"{package.name}.zip"
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(package.rglob("*"), key=lambda item: item.relative_to(package).as_posix()):
            if not path.is_file():
                continue
            relative = Path(package.name) / path.relative_to(package)
            info = zipfile.ZipInfo(relative.as_posix())
            info.create_system = 3
            mode = 0o755 if path.suffix == ".sh" else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    archive_path.parent.joinpath(f"{archive_path.name}.sha256").write_text(
        f"{sha256(archive_path)}  {archive_path.name}\n", encoding="utf-8", newline="\n",
    )
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 DataWork 自定义列服务器热补丁")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--latest", type=Path, default=DEFAULT_LATEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    baseline = args.baseline.expanduser().resolve()
    latest = args.latest.expanduser().resolve()
    output = args.output.expanduser().resolve()
    release_root = (ROOT / "发布包").resolve()
    if release_root not in output.parents:
        raise SystemExit(f"输出目录必须位于发布包目录内：{output}")
    for label, path in (("服务器基线", baseline), ("最新 Web 源码", latest)):
        if not (path / "datawork" / "core" / "plan.py").is_file():
            raise SystemExit(f"{label}不完整：{path}")
        if (path / "VERSION").read_text(encoding="utf-8").strip() != VERSION:
            raise SystemExit(f"{label}版本不是 {VERSION}：{path}")

    if output.exists():
        shutil.rmtree(output)
    payload = output / "payload"
    payload.mkdir(parents=True)
    copy_runtime_tree(latest / "datawork", payload / "datawork")
    for name in ROOT_FILES:
        source = latest / name
        if source.is_file():
            shutil.copy2(source, payload / name)

    baseline_map = runtime_map(baseline)
    latest_map = runtime_map(latest)
    added = sorted(latest_map.keys() - baseline_map.keys())
    modified = sorted(key for key in latest_map.keys() & baseline_map.keys() if latest_map[key] != baseline_map[key])
    deleted = sorted(baseline_map.keys() - latest_map.keys())
    if sorted(path for path in deleted if path in DELETE_PATHS) != sorted(DELETE_PATHS):
        raise RuntimeError(f"删除集合与审核结果不一致：{deleted}")

    (output / "DELETE_PATHS.txt").write_text("\n".join(DELETE_PATHS) + "\n", encoding="utf-8", newline="\n")
    write_normalized_manifest(baseline, BASELINE_GUARDS, output / "BASELINE_GUARDS_SHA256.txt")
    write_normalized_manifest(latest, TARGET_GUARDS, output / "TARGET_GUARDS_SHA256.txt")
    patch_info = {
        "patch_id": PATCH_ID,
        "version": VERSION,
        "site_root": "/www/wwwroot/1490473838.cn",
        "app_dir": "/www/wwwroot/1490473838.cn/datework",
        "source_main_commit": "18231162cd6575c1f355e7072e9c3a0432a75cea",
        "source_web_commit": "a94140932ea65f9ba6877ff9dab708101369aa6f",
        "baseline": str(baseline),
        "latest": str(latest),
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "excluded": [".venv/", "data/", "updates/", "*.sqlite3", "*.db", "API keys", "password hashes", "reports", "uploads"],
        "python_runtime_action": "reuse existing .venv; no Python download; no pip install",
    }
    (output / "PATCH_INFO.json").write_text(
        json.dumps(patch_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    (output / "应用热补丁.sh").write_text(installer_script(), encoding="utf-8", newline="\n")
    (output / "回滚本次热补丁.sh").write_text(rollback_script(), encoding="utf-8", newline="\n")
    (output / "热补丁说明.txt").write_text(instructions(), encoding="utf-8", newline="\n")
    write_sha_manifest(output)
    archive = build_zip(output)
    print(f"热补丁目录：{output}")
    print(f"热补丁 ZIP：{archive}")
    print(f"新增={len(added)}，修改={len(modified)}，删除={len(deleted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
