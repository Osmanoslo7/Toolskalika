#!/usr/bin/env python3
"""Word-level transcription of your talking head with faster-whisper (runs locally).

Called by `npm run transcribe`. Writes captions.auto.json; your edited
captions.json is managed by the Node side and never overwritten here.
The first run downloads the Whisper model from Hugging Face (free) into
~/.cache/huggingface; after that it works offline.
"""

import argparse
import hashlib
import json
import sys


def file_sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def words_from_segments(segments):
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if not text:
                continue
            words.append(
                {
                    "text": text,
                    "start": round(float(w.start), 3),
                    "end": round(float(w.end), 3),
                    "probability": round(float(w.probability), 3),
                }
            )
    return words


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio", required=True, help="16 kHz mono WAV from `npm run prep`")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--language", default="en")
    ap.add_argument("--prompt", default="", help="Vocabulary hint (brand names, jargon)")
    ap.add_argument("--device", default="auto", help="auto | cpu | cuda")
    ap.add_argument("--compute-type", default="default", help="e.g. int8 on CPU, float16 on CUDA")
    args = ap.parse_args(argv)

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print(
            "faster-whisper is not installed. Run:\n"
            "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 2

    compute_type = args.compute_type
    if compute_type == "default":
        compute_type = "int8" if args.device in ("auto", "cpu") else "float16"

    model = WhisperModel(args.model, device=args.device, compute_type=compute_type)
    segments, info = model.transcribe(
        args.audio,
        language=args.language or None,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
        condition_on_previous_text=False,
        initial_prompt=args.prompt or None,
    )
    words = words_from_segments(segments)

    result = {
        "model": args.model,
        "language": info.language,
        "duration": round(float(info.duration), 3),
        "audioHash": file_sha1(args.audio),
        "words": words,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Transcribed {len(words)} words ({info.duration:.1f}s) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
