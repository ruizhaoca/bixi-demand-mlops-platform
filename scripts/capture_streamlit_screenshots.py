"""Capture Streamlit page screenshots for the presentation deck.

Drives a running Streamlit app (default the local one on :8501) with the
Playwright Chromium that ships with the venv, clicks each sidebar page, triggers
the prediction views that need a button, and saves clean viewport captures to
docs/presentation/charts/streamlit_*.png.

Run (with the local app already serving on :8501):
    ./.venv/bin/python scripts/capture_streamlit_screenshots.py
    ./.venv/bin/python scripts/capture_streamlit_screenshots.py --url https://bixidemandlocal.streamlit.app/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "presentation" / "charts"
OUT.mkdir(parents=True, exist_ok=True)

VIEWPORT = {"width": 1600, "height": 1150}


def _wait_settled(page, pause: float = 2.5) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PWTimeout:
        pass
    page.wait_for_timeout(int(pause * 1000))


def _open_page(page, label: str) -> None:
    """Click a sidebar radio option by its visible label."""
    page.get_by_text(label, exact=True).first.click()
    _wait_settled(page)


def _click_primary(page, name_substr: str) -> None:
    try:
        btn = page.get_by_role("button", name=name_substr)
        btn.first.click(timeout=8_000)
        _wait_settled(page, pause=3.0)
    except PWTimeout:
        print(f"   (button '{name_substr}' not clicked — continuing)")


def _shot(page, name: str) -> None:
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(400)
    path = OUT / name
    page.screenshot(path=str(path))
    print(f"wrote {path.relative_to(REPO)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8501")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
                  "--use-gl=angle", "--force-color-profile=srgb"],
        )
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page = ctx.new_page()
        print(f"· loading {args.url}")
        page.goto(args.url, wait_until="domcontentloaded", timeout=60_000)
        # Streamlit Community Cloud "this app has gone to sleep" wake screen.
        try:
            wake = page.get_by_role("button", name="get this app back up")
            if wake.count():
                print("   waking sleeping Cloud app…")
                wake.first.click(timeout=8_000)
                page.wait_for_timeout(8_000)
        except Exception:  # noqa: BLE001
            pass
        # Streamlit Cloud wakeup / first render.
        try:
            page.get_by_text("BIXI Demand", exact=False).first.wait_for(timeout=90_000)
        except PWTimeout:
            print("   (sidebar title not seen — continuing anyway)")
        _wait_settled(page, pause=4.0)

        # 1. 7-Day forecast — show the full-day forecast chart.
        print("· 7-Day Demand Prediction")
        try:
            _open_page(page, "7-Day Demand Prediction")
            page.get_by_role("tab", name="Prediction for a Day").click(timeout=8_000)
            _wait_settled(page, pause=1.5)
            _click_primary(page, "Predict full day")
            _shot(page, "streamlit_7day_forecast.png")
        except Exception as exc:  # noqa: BLE001
            print(f"   ! 7-day failed: {exc}")

        # 2. Rebalancing priorities — map + ranked table render on load.
        print("· Rebalancing Priorities")
        try:
            _open_page(page, "Rebalancing Priorities")
            _wait_settled(page, pause=4.0)
            _shot(page, "streamlit_rebalancing.png")
        except Exception as exc:  # noqa: BLE001
            print(f"   ! rebalancing failed: {exc}")

        # 3. Custom inputs — trigger a what-if prediction.
        print("· Demand Prediction with Custom Inputs")
        try:
            _open_page(page, "Demand Prediction with Custom Inputs")
            _click_primary(page, "Predict")
            _shot(page, "streamlit_custom_inputs.png")
        except Exception as exc:  # noqa: BLE001
            print(f"   ! custom inputs failed: {exc}")

        # 4. Predictive Model Monitoring — metrics + SHAP/fairness/drift on load.
        print("· Predictive Model Monitoring")
        try:
            _open_page(page, "Predictive Model Monitoring")
            _wait_settled(page, pause=3.0)
            _shot(page, "streamlit_monitoring.png")
        except Exception as exc:  # noqa: BLE001
            print(f"   ! monitoring failed: {exc}")

        ctx.close()
        browser.close()
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
