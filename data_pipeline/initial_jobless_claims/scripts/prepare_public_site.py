#!/usr/bin/env python3
import shutil
from pathlib import Path

# Resolve paths relative to this script so it works on any machine/CI runner.
ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / 'dashboard'
DATA = ROOT / 'data' / 'raw' / 'macromicro' / 'chart19_all_series_latest.csv'
OUT = ROOT / 'public_site'


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    if not DATA.exists():
        raise FileNotFoundError(f'Missing data file: {DATA}')

    reset_dir(OUT)

    for name in ('index.html', 'style.css', 'app.js'):
        shutil.copy2(DASH / name, OUT / name)

    shutil.copy2(DATA, OUT / 'chart19_all_series_latest.csv')

    # Minimal no-jekyll marker for static hosts.
    (OUT / '.nojekyll').write_text('', encoding='utf-8')

    print(f'Prepared public site: {OUT}')
    print(f'Included data rows file: {OUT / "chart19_all_series_latest.csv"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
