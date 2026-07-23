#!/usr/bin/env python3
"""Build the verified DataWork V1.7 multi-baseline server hotfix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tomllib


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from package_server_v15_hotfix import (  # noqa: E402
    ROOT,
    ROOT_FILES,
    build_zip,
    copy_runtime,
    git_value,
    restart_service_function,
    runtime_map,
    sha256,
    verify_package,
    verify_simulated_apply,
    write_manifest,
    write_sha_manifest,
)


VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
PATCH_ID = "datawork_v1.7_core_audit_manova_combinations_20260724"
PACKAGE_NAME = "DataWork-v1.7-计算核心与MANOVA因变量组合-服务器热补丁-20260724"
DEFAULT_OUTPUT = ROOT / "发布包" / PACKAGE_NAME
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
    (
        "1.5.0-pairing-hotfix",
        ROOT
        / "发布包"
        / "DataWork-v1.5-配对映射与联合因变量-服务器热补丁-20260723"
        / "payload",
    ),
    (
        "1.5.0-website-package",
        ROOT / "发布包" / "DataWork-v1.5.0-网站部署版本" / "DataWork服务",
    ),
)
ACCEPTED_BASELINE_VERSIONS = ("0.4.9", "1.0.0", "1.5.0")
EXPECTED_DELETE_PATHS = {
    "datawork/ui.py",
    "datawork/web/static/assets/index-BkO9JSkG.css",
    "datawork/web/static/assets/index-C9-Qod4X.js",
    "datawork/web/static/assets/index-CPsr4TFv.js",
    "datawork/web/static/assets/index-Cnt-pWU9.js",
    "datawork/web/static/assets/index-DALge41P.js",
    "datawork/web/static/assets/index-exXYDQAE.css",
    "datawork/web/static/assets/index-mCJiNXhg.css",
}


def project_dependencies(root: Path) -> tuple[str, ...]:
    with (root / "pyproject.toml").open("rb") as handle:
        payload = tomllib.load(handle)
    return tuple(sorted(str(item) for item in payload["project"]["dependencies"]))


def verify_runtime_dependency_compatibility(baselines: list[tuple[str, Path, dict[str, str]]]) -> None:
    target = project_dependencies(ROOT)
    for name, path, _mapping in baselines:
        if project_dependencies(path) != target:
            raise RuntimeError(
                f"{name} 的正式运行依赖与 V1.7 不一致，不能承诺复用现有 .venv"
            )


def installer_script() -> str:
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
BACKUP_MARKER="$APP_DIR/updates/.last_v17_core_manova_hotfix_backup"
HEALTH_URL="http://127.0.0.1:8765/api/health"
OPENAPI_URL="http://127.0.0.1:8765/openapi.json"
ROOT_FILES=(
{root_files}
)
ACCEPTED_VERSIONS=({accepted_versions})

log() {{ printf '[DataWork V1.7 热补丁] %s\\n' "$*"; }}
fail() {{ printf '[DataWork V1.7 热补丁] 错误：%s\\n' "$*" >&2; exit 1; }}
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
  || fail "服务器版本 $CURRENT_VERSION 不在本补丁支持范围（0.4.9 / 1.0.0 / 1.5.0）。"

BASELINE_NAME="$(match_known_baseline || true)"
if [[ -z "$BASELINE_NAME" ]]; then
  if [[ "${{DATAWORK_ALLOW_BASELINE_MISMATCH:-0}}" != "1" ]]; then
    fail "服务器程序文件与五套已审核基线均不一致。安装已停止，未覆盖任何文件。"
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

log "覆盖 V1.7 运行源码；保留 .venv、data、updates、数据库和用户配置……"
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

log "使用现有虚拟环境执行 V1.7 离线功能烟雾测试……"
(
  cd "$APP_DIR"
  PYTHONDONTWRITEBYTECODE=1 DATAWORK_HOME="$APP_DIR/data" \
    "$APP_DIR/.venv/bin/python" - <<'PY'
import pandas as pd
import datawork
from datawork.application.analysis_service import AnalysisService
from datawork.application.preflight_service import PreflightService
from datawork.core.method_registry import MethodStatus, list_methods
from datawork.core.plan import AnalysisPlan

assert datawork.__version__ == "1.7.0"
methods = [item for item in list_methods() if item.visible and item.is_runnable]
assert len(methods) == 47
assert all(item.status is MethodStatus.IMPLEMENTED for item in methods)

frame = pd.DataFrame({{
    "group": ["A"] * 8 + ["B"] * 8,
    "y1": [1.0, 1.4, 1.8, 2.1, 2.5, 2.9, 3.2, 3.7, 4.2, 4.7, 5.1, 5.6, 6.0, 6.5, 7.0, 7.4],
    "y2": [3.2, 2.8, 3.6, 3.1, 4.0, 3.7, 4.4, 4.1, 5.0, 5.8, 5.3, 6.2, 5.9, 6.8, 6.4, 7.3],
    "y3": [5.1, 5.7, 4.8, 6.2, 5.5, 6.5, 5.9, 6.8, 7.1, 6.6, 7.8, 7.3, 8.4, 7.9, 8.8, 8.2],
    "y4": [2.4, 2.0, 2.9, 3.3, 2.7, 3.8, 3.1, 4.2, 4.8, 5.4, 4.9, 6.0, 5.6, 6.7, 6.1, 7.2],
}})
plan = AnalysisPlan(
    interface_mode="professional",
    method="oneway_manova",
    dependent_variables=["y1", "y2", "y3", "y4"],
    fixed_factors=["group"],
    dependent_task_mode="combinations",
    dependent_combination_min_size=2,
    dependent_combination_max_size=2,
    cross_model_p_adjust="holm",
)
report = PreflightService().inspect(frame, plan.model_dump(mode="json"))
assert report.ready
assert report.batch_summary["dependent_combination_count"] == 6
assert report.batch_summary["expanded_task_count"] == 6
result = AnalysisService().run(frame, plan)
assert len(result.results) == 6
assert all(item.result is not None and not item.error for item in result.results)
print("offline_v17_smoke=passed")
PY
)

if ! restart_service; then
  log "文件、哈希和离线测试均已完成，但未识别到进程守护名称。"
  log "请在宝塔进程守护管理器中手动重启 DataWork，再执行："
  log "curl -fsS $HEALTH_URL"
  exit 2
fi

log "等待 V1.7 服务恢复……"
for _ in $(seq 1 30); do
  if health_json="$(curl -fsS "$HEALTH_URL" 2>/dev/null)" \
    && printf '%s' "$health_json" | "$APP_DIR/.venv/bin/python" -c \
      'import json,sys; p=json.load(sys.stdin); assert p["status"]=="ok"; assert p["version"]=="1.7.0"; f=p["features"]; assert f["pairing_workflow"] is True; assert f["pairing_abs"] is True; assert f["dependent_variable_groups"] is True; assert f["dependent_variable_combinations"] is True' \
    && curl -fsS "$OPENAPI_URL" | grep -q '/api/preflight'; then
    log "更新成功：版本、V1.7 组合能力和预检接口均已加载。"
    log "备份位置：$BACKUP_DIR"
    exit 0
  fi
  sleep 1
done
fail "服务未在 30 秒内通过 V1.7 健康检查；请查看进程日志，必要时运行 ./回滚本次热补丁.sh。"
'''


def rollback_script() -> str:
    root_files = "\n".join(f'  "{item}"' for item in ROOT_FILES)
    return f'''#!/usr/bin/env bash
set -Eeuo pipefail

DEFAULT_APP_DIR="/www/wwwroot/1490473838.cn/datework"
APP_DIR="${{DATAWORK_APP_DIR:-$DEFAULT_APP_DIR}}"
SERVICE_NAME="${{DATAWORK_SUPERVISOR_NAME:-}}"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_MARKER="$APP_DIR/updates/.last_v17_core_manova_hotfix_backup"
HEALTH_URL="http://127.0.0.1:8765/api/health"
ROOT_FILES=(
{root_files}
)

log() {{ printf '[DataWork V1.7 热补丁回滚] %s\\n' "$*"; }}
fail() {{ printf '[DataWork V1.7 热补丁回滚] 错误：%s\\n' "$*" >&2; exit 1; }}

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
  log "请在宝塔面板手动重启 DataWork。"
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
    return f"""DataWork {VERSION} 计算核心审计与 MANOVA 因变量组合服务器热补丁
================================================================

默认目标路径：/www/wwwroot/1490473838.cn/datework

支持并已模拟验证的基线：
1. 原始 DataWork 0.4.9 服务器源码；
2. 已安装“自定义列与拆分继承”热补丁的 0.4.9；
3. DataWork 1.0.0 网站部署版本；
4. DataWork 1.5 配对映射与联合因变量热补丁 payload；
5. DataWork 1.5.0 网站部署版本。

不支持未经留档的 V1.6 服务器副本；如服务器曾被人工修改或部署过其他
版本，脚本会在覆盖前停止。只有管理员人工审核差异后，才能使用文末的
显式覆盖开关。

主要更新：
- 全部 47 个用户可见计算核心完成审计，当前均为正式实现；
- 单、双、三和 4–8 因素 ANOVA/MANOVA 全链路加固；
- 专业模式 MANOVA 支持 2–N 个因变量的无序组合批量计算；
- 因变量组合 × 因素模型 × 实际拆分组统一展开；
- 超过 200 个任务强警告，超过 1000 个任务阻止执行；
- 跨模型校正默认 Holm；
- 页面、Excel、Markdown、JSON、ZIP 与 AI 使用一致组合标识；
- MANOVA 常数响应、响应/设计矩阵秩不足和无残差自由度返回明确错误；
- 保留 V1.5/V1.6 计划及配对 abs(...) 兼容语义；
- 版本与 Vue 生产静态资源更新到 1.7.0。

安全边界：
- 复用服务器现有 .venv；正式运行依赖与五套基线一致，不下载 Python，
  不执行 pip install；
- 不读取或覆盖 data/、数据库、上传文件、报告、工作区密码、AI 密钥、
  宝塔脚本和进程守护配置；
- 安装前校验 ZIP 及包内 SHA-256，并匹配五套已审核基线之一；
- 覆盖前完整备份 datawork 目录和根版本文件；
- 覆盖后先校验目标哈希，再在现有虚拟环境运行 47 方法状态与 6 组合
  MANOVA 离线烟雾测试；
- 支持一条命令回滚，备份目录保留供审计。

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

3. 若脚本返回代码 2，表示文件、哈希和离线测试已完成，但没有自动识别
   宝塔进程守护名称。请在宝塔面板手动重启 DataWork，然后验证：

   curl -fsS http://127.0.0.1:8765/api/health

正常结果应包含 version=1.7.0，以及：
- pairing_workflow=true
- pairing_abs=true
- dependent_variable_groups=true
- dependent_variable_combinations=true

回滚：

   cd /www/wwwroot/1490473838.cn/datework/updates/{PACKAGE_NAME}
   ./回滚本次热补丁.sh

只有在确认服务器代码曾被人工修改、并已人工审核差异后，才允许：

   DATAWORK_ALLOW_BASELINE_MISMATCH=1 ./应用热补丁.sh
"""


def verify_sensitive_boundaries(payload: Path) -> None:
    forbidden_names = {
        ".env",
        "ai_settings.json",
        "workspace.sqlite3",
        "workspace_auth.json",
    }
    forbidden_parts = {"data", "files", "reports", "updates", "uploads"}
    violations: list[str] = []
    for path in payload.rglob("*"):
        relative = path.relative_to(payload)
        if path.name in forbidden_names or any(part in forbidden_parts for part in relative.parts):
            violations.append(relative.as_posix())
    if violations:
        raise RuntimeError(f"payload 包含运行数据或敏感配置：{violations}")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 DataWork V1.7 多基线服务器热补丁")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    release_root = (ROOT / "发布包").resolve()
    if release_root not in output.parents:
        raise SystemExit(f"输出目录必须位于发布包目录：{release_root}")
    if VERSION != "1.7.0":
        raise SystemExit(f"当前源码版本必须是 1.7.0，实际为：{VERSION}")
    required = (
        ROOT / "datawork" / "core" / "task_expansion.py",
        ROOT / "datawork" / "application" / "batch_export_service.py",
        ROOT / "datawork" / "web" / "static" / "index.html",
    )
    if not all(path.is_file() for path in required):
        raise SystemExit("当前源码缺少 V1.7 组合任务、批量导出或生产前端")

    baselines: list[tuple[str, Path, dict[str, str]]] = []
    for name, path in BASELINES:
        resolved = path.resolve()
        if not (resolved / "datawork" / "core" / "plan.py").is_file():
            raise SystemExit(f"服务器基线不完整：{name} -> {resolved}")
        baselines.append((name, resolved, runtime_map(resolved)))
    verify_runtime_dependency_compatibility(baselines)

    if output.exists():
        shutil.rmtree(output)
    payload = output / "payload"
    copy_runtime(ROOT, payload)
    verify_sensitive_boundaries(payload)
    target_map = runtime_map(ROOT)
    write_manifest(target_map, output / "TARGET_SHA256.txt")
    for name, _path, mapping in baselines:
        write_manifest(mapping, output / "BASELINES" / f"{name}.sha256")

    baseline_keys = set().union(*(mapping.keys() for _, _, mapping in baselines))
    delete_paths = sorted(baseline_keys - target_map.keys())
    if set(delete_paths) != EXPECTED_DELETE_PATHS:
        raise RuntimeError(f"删除集合超出已审核范围：{delete_paths}")
    (output / "DELETE_PATHS.txt").write_text(
        "\n".join(delete_paths) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    baseline_diffs: dict[str, object] = {}
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
        "created_date": "2026-07-24",
        "site_root": "/www/wwwroot/1490473838.cn",
        "app_dir": "/www/wwwroot/1490473838.cn/datework",
        "accepted_versions": list(ACCEPTED_BASELINE_VERSIONS),
        "supported_baselines": [name for name, _path, _mapping in baselines],
        "source_branch": git_value("branch", "--show-current"),
        "source_commit": git_value("rev-parse", "HEAD"),
        "source_has_uncommitted_changes": bool(source_status),
        "source_state_note": (
            "validated V1.7 working tree; package integrity is locked by "
            "TARGET_SHA256.txt and SHA256SUMS.txt"
        ),
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
            "server process configuration",
        ],
        "python_runtime_action": (
            "reuse existing .venv; dependencies verified unchanged; "
            "no Python download; no pip install"
        ),
        "simulated_apply_and_rollback": simulation,
    }
    (output / "PATCH_INFO.json").write_text(
        json.dumps(patch_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output / "应用热补丁.sh").write_text(
        installer_script(),
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
                "runtime_dependencies_unchanged": True,
                "sensitive_runtime_files_excluded": True,
                "offline_smoke": (
                    "installer verifies version, 47 implemented methods, "
                    "and 6 MANOVA outcome-combination tasks"
                ),
                "status": (
                    "generated; SHA256SUMS and ZIP are verified before delivery"
                ),
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
