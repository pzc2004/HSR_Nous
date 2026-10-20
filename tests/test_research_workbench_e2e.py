from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from hsr_nous.research.core import ArtifactStore, CandidateTaskManager
from tests._research_builders import make_candidate_set

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="研究台 E2E 使用 POSIX 进程组")


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def research_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("workbench-research")
    manager = CandidateTaskManager(ArtifactStore(root / "artifacts"))
    started = manager.start(make_candidate_set((600.0, 550.0)))
    final = manager.wait_terminal(started["task_id"], timeout_s=120)
    assert final["status"] == "completed"
    return root


@pytest.fixture(scope="module")
def browser_page():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("无 playwright（研究台 E2E 跳过）")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            yield page
            browser.close()
    except Exception as error:
        pytest.skip(f"Chromium 不可用（研究台 E2E 跳过）：{error}")


@pytest.fixture(scope="module")
def server(research_root, browser_page):
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "hsr_nous.research.workbench.cli",
            "--research-root",
            str(research_root),
            "--port",
            str(port),
            "--no-open",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            try:
                with urllib.request.urlopen(base + "/", timeout=2):
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise AssertionError("研究台服务器未能启动")
        browser_page.goto(base, wait_until="networkidle")
        yield base
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=15)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def test_workbench_browser_task_chart_report_and_evidence(server, browser_page):
    page = browser_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.locator(".task-card").first.wait_for(timeout=15000)
    page.locator("svg.chart").wait_for(timeout=15000)
    assert page.locator(".task-card").count() == 1
    assert page.locator("tbody tr.clickable").count() == 2
    assert "128/128" in page.locator("#overview").inner_text()

    page.locator("tbody tr.clickable").first.click()
    page.locator("#trial h2").wait_for(timeout=10000)
    assert "单候选报告" in page.locator("#trial h2").inner_text()
    assert page.locator("#trial .metric").count() >= 4
    page.locator("[data-action='open-run']").first.click()
    page.locator("#evidence .event-row").first.wait_for(timeout=10000)
    page.locator("#evidence .event-row").first.click()
    page.locator("#detailPanel pre").wait_for(timeout=10000)
    assert page.locator("#detailPanel").inner_text()

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(server, wait_until="networkidle")
    page.locator("svg.chart").wait_for(timeout=15000)
    assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not errors, errors
