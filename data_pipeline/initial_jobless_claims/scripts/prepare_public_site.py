#!/usr/bin/env python3
import os
import shutil
from pathlib import Path

# Resolve paths relative to this script so it works on any machine/CI runner.
ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / 'dashboard'
DATA_DIR = ROOT / 'data' / 'raw' / 'macromicro'
OUT = ROOT / 'public_site'


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def resolve_data_files() -> list[Path]:
    files: list[Path] = []
    env_data = os.environ.get('INITIAL_JOBLESS_CLAIMS_DATA_FILE', '').strip()
    if env_data:
        p = Path(env_data).expanduser().resolve(strict=False)
        if p.exists():
            files.append(p)

    candidate_dirs = [
        DATA_DIR,
        Path.cwd() / 'data_pipeline' / 'initial_jobless_claims' / 'data' / 'raw' / 'macromicro',
    ]

    for d in candidate_dirs:
        d = d.resolve(strict=False)
        if not d.exists():
            continue
        for p in sorted(d.glob('chart*_all_series_latest.csv')):
            if p not in files:
                files.append(p)

    if files:
        return files

    checked = '\n'.join(f'  - {d.resolve(strict=False)}' for d in candidate_dirs)
    raise FileNotFoundError(
        'Missing chart CSV files. Checked directories:\n'
        f'{checked}\n'
        'Hint: ensure files like chart19_all_series_latest.csv exist.'
    )


def main() -> int:
    data_files = resolve_data_files()

    reset_dir(OUT)

    for name in ('index.html', 'style.css', 'app.js'):
        shutil.copy2(DASH / name, OUT / name)

    copied: list[Path] = []
    for data_file in data_files:
        dst = OUT / data_file.name
        shutil.copy2(data_file, dst)
        copied.append(dst)

    # Minimal no-jekyll marker for static hosts.
    (OUT / '.nojekyll').write_text('', encoding='utf-8')

    print(f'Prepared public site: {OUT}')
    for p in copied:
        print(f'Included data rows file: {p}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
