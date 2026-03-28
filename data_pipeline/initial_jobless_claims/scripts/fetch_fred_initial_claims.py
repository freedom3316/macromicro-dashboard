#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import io
import pathlib
import subprocess
import urllib.request
from urllib.error import URLError

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=ICSA"


def fetch_csv() -> str:
    req = urllib.request.Request(
        FRED_CSV_URL,
        headers={"User-Agent": "initial-claims-pipeline/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except URLError:
        # Fallback for environments with broken Python TLS trust store.
        completed = subprocess.run(
            ["curl", "-fsSL", FRED_CSV_URL],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout


def validate_csv(raw_text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(raw_text))
    if not reader.fieldnames:
        raise ValueError("Downloaded CSV has no headers.")
    date_key = "DATE" if "DATE" in reader.fieldnames else "observation_date"
    required = {date_key, "ICSA"}
    if not required.issubset(set(reader.fieldnames)):
        raise ValueError(
            f"Unexpected CSV schema. Expected headers containing {required}, got {reader.fieldnames}."
        )

    rows: list[dict[str, str]] = []
    for row in reader:
        date = (row.get(date_key) or "").strip()
        value = (row.get("ICSA") or "").strip()
        if not date:
            continue
        # Keep missing markers as-is (e.g., '.') for downstream normalization.
        rows.append({"DATE": date, "ICSA": value})
    if not rows:
        raise ValueError("Downloaded CSV had no data rows.")
    return rows


def write_outputs(rows: list[dict[str, str]], raw_text: str, out_dir: pathlib.Path) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    snapshot_path = out_dir / f"fred_icsa_{stamp}.csv"
    snapshot_path.write_text(raw_text, encoding="utf-8")

    latest_path = out_dir / "fred_icsa_latest.csv"
    with latest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["DATE", "ICSA"])
        writer.writeheader()
        writer.writerows(rows)

    return latest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch FRED Initial Claims (ICSA) CSV")
    parser.add_argument(
        "--out-dir",
        default="data_pipeline/initial_jobless_claims/data/raw/fred",
        help="Directory to save raw snapshots and latest CSV",
    )
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    raw_text = fetch_csv()
    rows = validate_csv(raw_text)
    latest_path = write_outputs(rows, raw_text, out_dir)
    print(f"Fetched {len(rows)} rows from FRED ICSA.")
    print(f"Updated latest file: {latest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
