#!/usr/bin/env bash
set -euo pipefail

# One-click transcription for XiaoYuzhou episode links (macOS arm64 + mlx-whisper).
# Usage:
#   bash xiaoyuzhou_oneclick.sh "<episode_url_or_audio_url>" [output_dir]
#
# Example:
#   bash xiaoyuzhou_oneclick.sh "https://www.xiaoyuzhoufm.com/episode/69ba2e32f8b8079bfaef73e5" ~/Desktop/asr_out

INPUT_URL="${1:-}"
OUT_DIR="${2:-$HOME/Desktop/asr_out}"
MODEL_REPO="${MODEL_REPO:-mlx-community/whisper-base-mlx}"  # or whisper-small-mlx
LANG="${LANG:-zh}"

if [[ -z "$INPUT_URL" ]]; then
  echo "Usage: bash xiaoyuzhou_oneclick.sh \"<episode_url_or_audio_url>\" [output_dir]"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found. Install with: brew install ffmpeg"
  exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Warning: current arch is not arm64. mlx-whisper may be slow or fail."
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

mkdir -p "$OUT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$HOME/venvs/asr-metal}"

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip -q install -U pip >/dev/null
python -m pip -q install mlx-whisper >/dev/null

HTML_FILE="$WORK_DIR/episode.html"
AUDIO_FILE="$WORK_DIR/audio.m4a"
TITLE_FILE="$WORK_DIR/title.txt"

extract_audio_url_from_html() {
  python - "$1" <<'PY'
import re, sys
from pathlib import Path
html = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
m = re.search(r'<meta\s+property="og:audio"\s+content="([^"]+)"', html, re.I)
if not m:
    m = re.search(r'"contentUrl":"(https://[^"]+\.(?:m4a|mp3|aac|wav))"', html)
print(m.group(1) if m else "")
PY
}

extract_title_from_html() {
  python - "$1" <<'PY'
import re, sys
from pathlib import Path
html = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
if not m:
    print("episode")
    raise SystemExit
t = m.group(1)
t = t.replace(" | 小宇宙 - 听播客，上小宇宙", "").strip()
print(t if t else "episode")
PY
}

sanitize_name() {
  python - "$1" <<'PY'
import re, sys
s = sys.argv[1].strip()
s = re.sub(r'[\\/:*?"<>|]+', "_", s)
s = re.sub(r"\s+", " ", s).strip()
print((s or "episode")[:100])
PY
}

if [[ "$INPUT_URL" =~ \.(m4a|mp3|aac|wav)(\?.*)?$ ]]; then
  AUDIO_URL="$INPUT_URL"
  TITLE="episode"
else
  echo "[1/5] Fetch episode page..."
  curl -L --max-time 60 "$INPUT_URL" -o "$HTML_FILE" >/dev/null 2>&1
  AUDIO_URL="$(extract_audio_url_from_html "$HTML_FILE")"
  RAW_TITLE="$(extract_title_from_html "$HTML_FILE")"
  TITLE="$(sanitize_name "$RAW_TITLE")"
  if [[ -z "$AUDIO_URL" ]]; then
    echo "Failed to extract audio URL from episode page."
    exit 1
  fi
fi

TARGET_DIR="$OUT_DIR/$TITLE"
mkdir -p "$TARGET_DIR"
TARGET_AUDIO="$TARGET_DIR/audio.m4a"
TARGET_FULL="$TARGET_DIR/transcript_full.txt"
TARGET_SEG="$TARGET_DIR/transcript_segments.md"

echo "[2/5] Download audio..."
curl -L -C - --max-time 1800 "$AUDIO_URL" -o "$AUDIO_FILE"
cp "$AUDIO_FILE" "$TARGET_AUDIO"

echo "[3/5] Transcribe with mlx-whisper..."
python - "$AUDIO_FILE" "$TARGET_FULL" "$TARGET_SEG" "$MODEL_REPO" "$LANG" <<'PY'
import os
import sys
from pathlib import Path
import mlx_whisper

audio = sys.argv[1]
full_out = Path(sys.argv[2])
seg_out = Path(sys.argv[3])
model_repo = sys.argv[4]
lang = sys.argv[5]

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/opt/anaconda3/bin:" + os.environ.get("PATH", "")

res = mlx_whisper.transcribe(
    audio,
    path_or_hf_repo=model_repo,
    language=lang,
)

text = (res.get("text") or "").strip()
full_out.write_text(text + ("\n" if text else ""), encoding="utf-8")

with seg_out.open("w", encoding="utf-8") as f:
    f.write(f"# Transcript\n\nModel: {model_repo}\nLanguage: {lang}\n\n")
    for s in res.get("segments", []):
        st = float(s.get("start", 0))
        ed = float(s.get("end", 0))
        t = (s.get("text") or "").strip()
        if t:
            f.write(f"[{st:8.2f} - {ed:8.2f}] {t}\n")
PY

echo "[4/5] Done."
echo "Output dir: $TARGET_DIR"
echo "Audio:      $TARGET_AUDIO"
echo "Full text:  $TARGET_FULL"
echo "Segments:   $TARGET_SEG"
echo "[5/5] Tip: set MODEL_REPO=mlx-community/whisper-small-mlx for higher quality."

