#!/usr/bin/env python3
"""Capture Platon gallery screenshots and demo video via Playwright."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "docs" / "screenshots"
RECORDINGS = ROOT / "docs" / "recordings"


def ensure_playwright() -> None:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])


def wait_for_stack(base: str, timeout: int = 60) -> None:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError("Backend not ready — run ./start.sh first")


def capture() -> None:
    ensure_playwright()
    from playwright.sync_api import sync_playwright

    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    RECORDINGS.mkdir(parents=True, exist_ok=True)

    base_api = os.environ.get("PLATON_API_URL", "http://127.0.0.1:9200")
    if os.environ.get("PLATON_CAPTURE_PROD") == "1":
        base_ui = os.environ.get("PLATON_UI_URL", "https://oracles.modelmarket.dev/platon/umbral")
    else:
        base_ui = os.environ.get("PLATON_UI_URL", "http://127.0.0.1:5174")

    try:
        wait_for_stack(base_api, timeout=5)
    except RuntimeError:
        print("▸ Starting backend for capture…")
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "platon.main:app", "--host", "127.0.0.1", "--port", "9200"],
            cwd=ROOT / "backend",
        )
        wait_for_stack(base_api)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        page = context.new_page()

        try:
            page.goto(base_ui, wait_until="networkidle", timeout=8000)
        except Exception:
            print("▸ Frontend not running — capturing API-only placeholder")
            page.set_content(
                "<html><body style='background:#050508;color:#6ee7ff;font-family:monospace;"
                "padding:2rem'><h1>Platon UMBRAL</h1><p>Run ./start.sh for full UI capture</p></body></html>"
            )

        page.wait_for_timeout(2000)

        en = page.get_by_test_id("lang-switch").get_by_role("button", name="EN")
        if en.count():
            en.click()
        page.wait_for_timeout(4000)

        page.screenshot(path=str(SCREENSHOTS / "01-main-view.png"), full_page=False)
        page.screenshot(path=str(SCREENSHOTS / "05-cosmos.png"), full_page=False)

        metrics = page.locator("[data-testid=metrics-panel]")
        if metrics.count():
            metrics.first.screenshot(path=str(SCREENSHOTS / "02-telemetry.png"))

        steer_panel = page.locator(".panel").filter(
            has=page.get_by_role("heading", name="Incarnation · semantic steering")
        )
        if steer_panel.count():
            steer_panel.first.screenshot(path=str(SCREENSHOTS / "03-steering.png"))

        witnesses = page.locator("[data-testid=witness-feed]")
        if witnesses.count():
            witnesses.first.screenshot(path=str(SCREENSHOTS / "04-witnesses.png"))

        video_dir = RECORDINGS / "_tmp"
        video_dir.mkdir(exist_ok=True)
        context = browser.new_context(
            record_video_dir=str(video_dir),
            record_video_size={"width": 1280, "height": 720},
        )
        vpage = context.new_page()
        try:
            vpage.goto(base_ui, timeout=8000)
        except Exception:
            vpage.set_content(page.content())
        vpage.wait_for_timeout(1500)
        if vpage.locator("[data-testid=steer-input]").count():
            vpage.locator("[data-testid=steer-input]").fill("entropy cathedral")
            vpage.locator("[data-testid=steer-btn]").click()
        vpage.wait_for_timeout(3000)
        vpage.close()
        context.close()

        videos = list(video_dir.glob("*.webm"))
        if videos:
            target = RECORDINGS / "platon-demo-latest.webm"
            videos[0].rename(target)
            print(f"▸ Video: {target}")

        browser.close()

    print(f"▸ Screenshots saved to {SCREENSHOTS}")


if __name__ == "__main__":
    capture()
