#!/usr/bin/python3
"""whisper_segments.py FILE [--start S] [--duration D] [--model small]

Transcribe with faster-whisper (in Daf's own environment: media.py runs this with Daf's Python) and
print JSON: {"language": "en", "segments": [{"start": s, "end": e, "text": "..."}]}.
--start/--duration cut a window first (ffmpeg), for clips and bookmarks."""
import argparse
import json
import os
import subprocess
import sys
import tempfile

from faster_whisper import WhisperModel

ap = argparse.ArgumentParser()
ap.add_argument("file")
ap.add_argument("--start", type=float, default=None)
ap.add_argument("--duration", type=float, default=None)
ap.add_argument("--model", default=os.environ.get("DAF_WHISPER_MODEL", "small"))
a = ap.parse_args()

src, tmp = a.file, None
if a.start is not None or a.duration is not None:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y"]
    if a.start is not None:
        cmd += ["-ss", str(max(0.0, a.start))]
    cmd += ["-i", a.file]
    if a.duration is not None:
        cmd += ["-t", str(a.duration)]
    cmd += ["-ac", "1", "-ar", "16000", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(json.dumps({"error": r.stderr.strip()[-300:]}))
        sys.exit(1)
    src = tmp
try:
    model = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=8)
    segments, info = model.transcribe(src, vad_filter=True)
    out = [{"start": round(s.start + (a.start or 0), 2), "end": round(s.end + (a.start or 0), 2), "text": s.text.strip()} for s in segments]
    print(json.dumps({"language": info.language, "segments": out}))
finally:
    if tmp:
        os.unlink(tmp)
