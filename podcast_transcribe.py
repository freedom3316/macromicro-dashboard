#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from faster_whisper import WhisperModel


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        print(p.stdout)
        raise RuntimeError(f"command failed: {' '.join(cmd)}")
    return p.stdout


def ensure_ffmpeg():
    for x in ["ffmpeg", "/opt/anaconda3/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if os.path.exists(x) or shutil_which(x):
            return x
    raise RuntimeError("ffmpeg not found")


def shutil_which(cmd):
    from shutil import which
    return which(cmd)


def sanitize(name):
    return re.sub(r"[^\w\-.]+", "_", name)[:80]


def download(url, out_file):
    out_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["curl", "-L", "-C", "-", "--max-time", "600", url, "-o", str(out_file)]
    print("[1/3] downloading audio...")
    run(cmd)


def transcribe(audio_file, model_name, language, out_txt, out_seg):
    print(f"[2/3] loading model: {model_name}")
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=8)
    print("[3/3] transcribing...")
    segments, info = model.transcribe(
        str(audio_file),
        language=language,
        vad_filter=True,
        beam_size=1 if model_name in {"tiny", "base"} else 5,
    )
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    with out_txt.open("w", encoding="utf-8") as ftxt, out_seg.open("w", encoding="utf-8") as fseg:
        fseg.write(f"# Transcript\n\nDetected language: {info.language} (p={info.language_probability:.3f})\n\n")
        for s in segments:
            text = s.text.strip()
            if not text:
                continue
            ftxt.write(text + "\n")
            fseg.write(f"[{s.start:8.2f} - {s.end:8.2f}] {text}\n")


def main():
    ap = argparse.ArgumentParser(description="Download podcast audio and transcribe locally")
    ap.add_argument("audio_url", help="direct audio URL, e.g. m4a/mp3")
    ap.add_argument("--name", default="episode")
    ap.add_argument("--model", default="tiny", choices=["tiny", "base", "small"])
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--outdir", default="./outputs")
    args = ap.parse_args()

    outdir = Path(args.outdir).expanduser().resolve() / sanitize(args.name)
    audio_file = outdir / "audio.m4a"
    out_txt = outdir / "transcript_full.txt"
    out_seg = outdir / "transcript_segments.md"

    download(args.audio_url, audio_file)
    transcribe(audio_file, args.model, args.lang, out_txt, out_seg)

    print("done")
    print(f"audio: {audio_file}")
    print(f"full:  {out_txt}")
    print(f"seg:   {out_seg}")


if __name__ == "__main__":
    main()
