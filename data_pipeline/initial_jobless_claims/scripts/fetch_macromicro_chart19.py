#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://www.macromicro.me/collections/4/us-employ-relative/19/initial-jobless-claims"
CHART_API = "https://www.macromicro.me/charts/data/19"

# Based on observed structure from chart 19.
SERIES_LABELS = {
    0: "initial_jobless_claims",
    1: "continuing_jobless_claims",
    2: "initial_jobless_claims_4w_avg",
}


def clone_chrome_profile(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    cmd = [
        "rsync",
        "-a",
        "--exclude=Singleton*",
        "--exclude=*/Sessions/*",
        "--exclude=*/Session Storage/*",
        "--exclude=*/Cache/*",
        "--exclude=*/Code Cache/*",
        "--exclude=*/GPUCache/*",
        "--exclude=*/Service Worker/CacheStorage/*",
        "--exclude=*/ShaderCache/*",
        f"{str(src)}/",
        f"{str(dst)}/",
    ]
    subprocess.run(cmd, check=False)


def fetch_chart_json(user_data_dir: Path, wait_ms: int = 35000) -> dict:
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            channel="chrome",
            headless=False,
            ignore_default_args=["--enable-automation"],
            args=[
                "--profile-directory=Default",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(wait_ms)

        title = page.title()
        if "请稍候" in title or "Just a moment" in title:
            context.close()
            raise RuntimeError("Cloudflare challenge page still active. Retry the script.")

        payload = page.evaluate(
            """async (api) => {
                const r = await fetch(api, {credentials: 'include'});
                return await r.json();
            }""",
            CHART_API,
        )
        context.close()
    return payload


def to_rows(payload: dict) -> tuple[list[dict], list[dict]]:
    chart = payload["data"]["c:19"]
    info = chart.get("info", {})
    ingested_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_rows: list[dict] = []
    initial_rows: list[dict] = []

    for idx, series_data in enumerate(chart.get("series", [])):
        label = SERIES_LABELS.get(idx, f"series_{idx}")
        for date_str, value_str in series_data:
            try:
                value = float(value_str)
            except Exception:
                continue
            row = {
                "date": date_str,
                "value": value,
                "series_index": idx,
                "series_label": label,
                "chart_id": 19,
                "chart_name_en": info.get("name_en", ""),
                "source": "macromicro",
                "ingested_at": ingested_at,
            }
            all_rows.append(row)
            if idx == 0:
                initial_rows.append(row)

    all_rows.sort(key=lambda r: (r["series_index"], r["date"]))
    initial_rows.sort(key=lambda r: r["date"])
    return all_rows, initial_rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise RuntimeError(f"No rows to write: {path}")
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch MacroMicro chart 19 via logged-in Chrome session")
    parser.add_argument(
        "--chrome-profile-src",
        default=str(Path.home() / "Library/Application Support/Google/Chrome"),
        help="Source Chrome user data dir",
    )
    parser.add_argument(
        "--work-profile-dir",
        default="/Users/freedom33/Documents/New project/.tmp_chrome_profile",
        help="Temporary copied profile dir used by Playwright",
    )
    parser.add_argument(
        "--out-dir",
        default="/Users/freedom33/Documents/New project/data_pipeline/initial_jobless_claims/data/raw/macromicro",
        help="Output directory",
    )
    args = parser.parse_args()

    src = Path(args.chrome_profile_src)
    work = Path(args.work_profile_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    clone_chrome_profile(src, work)
    payload = fetch_chart_json(work)

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_json = out_dir / f"chart19_raw_{stamp}.json"
    raw_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    all_rows, initial_rows = to_rows(payload)
    write_csv(all_rows, out_dir / "chart19_all_series_latest.csv")
    write_csv(initial_rows, out_dir / "chart19_initial_claims_latest.csv")

    print(f"Saved raw JSON: {raw_json}")
    print(f"All series rows: {len(all_rows)}")
    print(f"Initial claims rows: {len(initial_rows)}")
    print(f"Initial latest: {initial_rows[-1]['date']} {initial_rows[-1]['value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
