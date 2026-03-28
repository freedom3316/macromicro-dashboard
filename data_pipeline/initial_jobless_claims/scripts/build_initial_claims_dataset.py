#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import hashlib
import pathlib
import sqlite3
from typing import Iterable


DATE_CANDIDATES = ["date", "DATE", "Date", "time", "Time", "日期"]
VALUE_CANDIDATES = [
    "value",
    "VALUE",
    "Value",
    "ICSA",
    "initial jobless claims",
    "Initial Jobless Claims",
    "初次申请失业金人数",
    "初请失业金人数",
]


def _first_matching_key(keys: Iterable[str], candidates: list[str]) -> str | None:
    keyset = list(keys)
    low_map = {k.lower(): k for k in keyset}
    for c in candidates:
        if c in keyset:
            return c
        lk = c.lower()
        if lk in low_map:
            return low_map[lk]
    return None


def _parse_date(v: str) -> str | None:
    v = (v or "").strip()
    if not v:
        return None

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%Y.%m.%d",
    ]
    for fmt in formats:
        try:
            return dt.datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            pass

    try:
        return dt.date.fromisoformat(v).isoformat()
    except ValueError:
        return None


def _parse_value(v: str) -> float | None:
    v = (v or "").strip()
    if not v or v == ".":
        return None
    v = v.replace(",", "")
    try:
        return float(v)
    except ValueError:
        return None


def _hash_record(date: str, value: float, source: str, series_code: str) -> str:
    payload = f"{date}|{value}|{source}|{series_code}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_fred_rows(path: pathlib.Path, ingested_at: str) -> list[dict]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []

        out: list[dict] = []
        for row in reader:
            d = _parse_date(row.get("DATE", ""))
            v = _parse_value(row.get("ICSA", ""))
            if d is None or v is None:
                continue
            out.append(
                {
                    "date": d,
                    "value": v,
                    "series_code": "ICSA",
                    "series_name": "Initial Claims",
                    "unit": "Number",
                    "frequency": "weekly",
                    "seasonal_adjustment": "SA",
                    "source": "fred",
                    "ingested_at": ingested_at,
                    "version_hash": _hash_record(d, v, "fred", "ICSA"),
                }
            )
    return out


def load_macromicro_rows(raw_dir: pathlib.Path, ingested_at: str) -> list[dict]:
    if not raw_dir.exists():
        return []

    out: list[dict] = []
    for csv_path in sorted(raw_dir.glob("*.csv")):
        with csv_path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                continue

            date_key = _first_matching_key(reader.fieldnames, DATE_CANDIDATES)
            value_key = _first_matching_key(reader.fieldnames, VALUE_CANDIDATES)
            series_label_key = _first_matching_key(
                reader.fieldnames, ["series_label", "Series Label", "series"]
            )

            if not date_key or not value_key:
                continue

            for row in reader:
                if series_label_key:
                    label = (row.get(series_label_key) or "").strip().lower()
                    if label and label not in (
                        "initial_jobless_claims",
                        "initial claims",
                        "initial jobless claims",
                    ):
                        continue
                d = _parse_date(row.get(date_key, ""))
                v = _parse_value(row.get(value_key, ""))
                if d is None or v is None:
                    continue

                out.append(
                    {
                        "date": d,
                        "value": v,
                        "series_code": "US_INITIAL_JOBLESS_CLAIMS",
                        "series_name": "Initial Jobless Claims",
                        "unit": "Number",
                        "frequency": "weekly",
                        "seasonal_adjustment": "unknown",
                        "source": "macromicro",
                        "ingested_at": ingested_at,
                        "version_hash": _hash_record(
                            d, v, "macromicro", "US_INITIAL_JOBLESS_CLAIMS"
                        ),
                    }
                )
    return out


def dedupe_rows(rows: list[dict]) -> list[dict]:
    # Keep latest ingested row for same (date, series_code, source).
    key_to_row: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        k = (row["date"], row["series_code"], row["source"])
        prev = key_to_row.get(k)
        if prev is None or row["ingested_at"] >= prev["ingested_at"]:
            key_to_row[k] = row
    return sorted(key_to_row.values(), key=lambda r: (r["date"], r["source"]))


def write_processed_csv(rows: list[dict], out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "date",
        "value",
        "series_code",
        "series_name",
        "unit",
        "frequency",
        "seasonal_adjustment",
        "source",
        "ingested_at",
        "version_hash",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_sqlite(rows: list[dict], db_path: pathlib.Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS initial_jobless_claims (
                date TEXT NOT NULL,
                value REAL NOT NULL,
                series_code TEXT NOT NULL,
                series_name TEXT NOT NULL,
                unit TEXT NOT NULL,
                frequency TEXT NOT NULL,
                seasonal_adjustment TEXT NOT NULL,
                source TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                version_hash TEXT NOT NULL,
                PRIMARY KEY (date, series_code, source)
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO initial_jobless_claims (
                date, value, series_code, series_name, unit,
                frequency, seasonal_adjustment, source,
                ingested_at, version_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, series_code, source) DO UPDATE SET
                value=excluded.value,
                series_name=excluded.series_name,
                unit=excluded.unit,
                frequency=excluded.frequency,
                seasonal_adjustment=excluded.seasonal_adjustment,
                ingested_at=excluded.ingested_at,
                version_hash=excluded.version_hash
            """,
            [
                (
                    r["date"],
                    r["value"],
                    r["series_code"],
                    r["series_name"],
                    r["unit"],
                    r["frequency"],
                    r["seasonal_adjustment"],
                    r["source"],
                    r["ingested_at"],
                    r["version_hash"],
                )
                for r in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build standardized initial claims dataset")
    parser.add_argument(
        "--fred-latest",
        default="data_pipeline/initial_jobless_claims/data/raw/fred/fred_icsa_latest.csv",
        help="Path to latest FRED CSV file",
    )
    parser.add_argument(
        "--macromicro-dir",
        default="data_pipeline/initial_jobless_claims/data/raw/macromicro",
        help="Directory containing MacroMicro CSV exports",
    )
    parser.add_argument(
        "--out-csv",
        default="data_pipeline/initial_jobless_claims/data/processed/initial_jobless_claims.csv",
        help="Output standardized CSV path",
    )
    parser.add_argument(
        "--out-db",
        default="data_pipeline/initial_jobless_claims/data/processed/initial_jobless_claims.sqlite",
        help="Output SQLite path",
    )
    args = parser.parse_args()

    ingested_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = []
    rows.extend(load_fred_rows(pathlib.Path(args.fred_latest), ingested_at))
    rows.extend(load_macromicro_rows(pathlib.Path(args.macromicro_dir), ingested_at))
    rows = dedupe_rows(rows)

    write_processed_csv(rows, pathlib.Path(args.out_csv))
    write_sqlite(rows, pathlib.Path(args.out_db))

    print(f"Built dataset with {len(rows)} rows.")
    print(f"CSV: {args.out_csv}")
    print(f"SQLite: {args.out_db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
