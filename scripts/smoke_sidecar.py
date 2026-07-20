"""从源码目录之外验证 PyInstaller sidecar 的启动、分析和报告链路。"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

import httpx


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_for_health(base_url: str, process: subprocess.Popen[bytes], timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"sidecar 提前退出，退出码 {process.returncode}")
        try:
            response = httpx.get(f"{base_url}/api/health", timeout=2)
            if response.status_code == 200:
                return response.json()
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"sidecar 在 {timeout:g} 秒内未就绪：{last_error}")


def _stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if sys.platform.startswith("win"):
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--expected-version", default="")
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    if not artifact.is_file():
        raise SystemExit(f"sidecar 不存在: {artifact}")

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    csv_data = (
        "group,value\n"
        "A,1.0\nA,1.2\nA,1.1\nA,1.3\n"
        "B,2.0\nB,2.2\nB,2.1\nB,2.3\n"
        "C,3.0\nC,3.2\nC,3.1\nC,3.3\n"
    ).encode("utf-8")
    plan = {
        "dependent_variables": ["value"],
        "fixed_factors": ["group"],
        "method": "oneway_anova",
        "method_parameters": {"posthoc_methods": ["tukey"]},
    }

    with tempfile.TemporaryDirectory(prefix="datawork-sidecar-smoke-") as raw_temp:
        temp = Path(raw_temp)
        log_path = temp / "sidecar.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [
                    str(artifact), "--host", "127.0.0.1", "--port", str(port),
                    "--workspace", str(temp / "workspace"), "--no-browser",
                ],
                cwd=temp,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                health = _wait_for_health(base_url, process, args.timeout)
                if args.expected_version and health.get("version") != args.expected_version:
                    raise RuntimeError(f"sidecar 版本异常: {health}")
                capabilities = httpx.get(f"{base_url}/api/capabilities", timeout=10)
                capabilities.raise_for_status()
                method_count = int(capabilities.json().get("statistics", {}).get("runnable_method_count", 0))
                if method_count < 46:
                    raise RuntimeError("sidecar 方法清单不完整")

                analysis = httpx.post(
                    f"{base_url}/api/analyze",
                    files={"file": ("smoke.csv", csv_data, "text/csv")},
                    data={"plan_json": json.dumps(plan)},
                    timeout=60,
                )
                analysis.raise_for_status()
                execution = analysis.json()
                if execution.get("kind") != "single":
                    raise RuntimeError(f"sidecar 分析结果类型异常: {execution.get('kind')}")

                report = httpx.post(
                    f"{base_url}/api/instant/reports",
                    json={"execution": execution, "title": "DataWork sidecar smoke"},
                    timeout=60,
                )
                report.raise_for_status()
                archive = httpx.get(f"{base_url}{report.json()['download_url']}", timeout=30)
                archive.raise_for_status()
                with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
                    required = {"results.xlsx", "statistical_report.md", "canonical_result.json"}
                    if not required.issubset(bundle.namelist()):
                        raise RuntimeError("sidecar 报告 ZIP 内容不完整")
                print(
                    f"sidecar smoke passed: version={health['version']}, "
                    f"methods={method_count}, port={port}"
                )
            except Exception as exc:
                log.flush()
                detail = log_path.read_text(encoding="utf-8", errors="replace")[-6000:]
                raise SystemExit(f"sidecar 冒烟失败: {exc}\n--- sidecar log ---\n{detail}") from exc
            finally:
                _stop_process_tree(process)


if __name__ == "__main__":
    main()
