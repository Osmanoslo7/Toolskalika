"""Phase 3 — render candidate clips with FFmpeg.

One FFmpeg call per clip and preset: input seek, trim, reframe, optional burned-in
subtitles, fades, two-pass loudness normalisation, H.264 + AAC with +faststart.
Sources are only read; outputs go to <workspace>/renders/<media_id>/.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from . import ffmpeg
from .config import workspace
from .metrics import stage

# --- subtitles -----------------------------------------------------------------------------

_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def _secs(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    entries = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = block.strip().split("\n")
        for i, line in enumerate(lines):
            m = _TS.search(line)
            if m:
                body = "\n".join(lines[i + 1:]).strip()
                if body:
                    entries.append((_secs(*m.groups()[:4]), _secs(*m.groups()[4:]), body))
                break
    return entries


def _fmt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def shift_srt(entries, start: float, end: float) -> str:
    """Keep cues overlapping [start, end] and re-time them to clip time."""
    out, n = [], 0
    for a, b, body in entries:
        if b <= start or a >= end:
            continue
        n += 1
        out.append(f"{n}\n{_fmt(max(a, start) - start)} --> {_fmt(min(b, end) - start)}\n{body}\n")
    return "\n".join(out)


def sidecar_srt(media_path: str) -> Path | None:
    p = Path(media_path).with_suffix(".srt")
    return p if p.is_file() else None


# --- filters -------------------------------------------------------------------------------

def video_filter(mode: str, w: int, h: int) -> str:
    if mode == "fit":
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
    if mode == "crop":
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    if mode == "blur":
        return (f"split=2[bg0][fg0];[bg0]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"boxblur=20:2[bg];[fg0]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    raise ValueError(mode)


def measure_loudness(src: str, start: float, dur: float, lcfg: dict) -> dict | None:
    """First loudnorm pass over the clip's audio. None if silent/unmeasurable."""
    proc = ffmpeg.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
                       "-i", src, "-vn", "-sn",
                       "-af", f"loudnorm=I={lcfg['integrated']}:TP={lcfg['true_peak']}:LRA={lcfg['lra']}"
                              ":print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr)
    if not m:
        return None
    data = json.loads(m.group(0))
    try:
        if float(data["input_i"]) < -70:   # effectively silent; normalising would amplify noise
            return None
    except ValueError:                     # "-inf"
        return None
    return data


def build_command(src: str, out: Path, start: float, dur: float, preset: dict, rcfg: dict,
                  has_audio: bool, loud: dict | None, srt_name: str | None) -> list[str]:
    w, h = preset["width"], preset["height"]
    fi = min(rcfg["fade_in_s"], dur / 3)
    fo = min(rcfg["fade_out_s"], dur / 3)
    vf = video_filter(preset["mode"], w, h) + f",fps={rcfg['fps']}"
    if srt_name:
        st = rcfg["subtitles"]
        vertical = h > w
        size = st["font_size_vertical"] if vertical else st["font_size"]
        margin = int(288 * (st["bottom_margin_vertical"] if vertical else st["bottom_margin"]))
        vf += f",subtitles=filename={srt_name}:force_style='FontSize={size},MarginV={margin}'"
    if fi > 0:
        vf += f",fade=t=in:st=0:d={fi:.3f}"
    if fo > 0:
        vf += f",fade=t=out:st={dur - fo:.3f}:d={fo:.3f}"
    vf += ",format=yuv420p"

    lc = rcfg["loudness"]
    if loud:
        af = (f"loudnorm=I={lc['integrated']}:TP={lc['true_peak']}:LRA={lc['lra']}"
              f":measured_I={loud['input_i']}:measured_TP={loud['input_tp']}"
              f":measured_LRA={loud['input_lra']}:measured_thresh={loud['input_thresh']}"
              f":offset={loud['target_offset']}:linear=true")
    else:
        af = "anull"
    if fi > 0:
        af += f",afade=t=in:st=0:d={fi:.3f}"
    if fo > 0:
        af += f",afade=t=out:st={dur - fo:.3f}:d={fo:.3f}"
    af += f",aresample={rcfg['audio']['sample_rate']},aformat=channel_layouts=stereo"

    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src]
    if not has_audio:  # keep every output consistent: always a (silent) stereo track
        cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i",
                f"anullsrc=r={rcfg['audio']['sample_rate']}:cl=stereo"]
    a_in = "0:a:0" if has_audio else "1:a:0"
    v = rcfg["video"]
    cmd += ["-filter_complex", f"[0:v:0]{vf}[v];[{a_in}]{af}[a]", "-map", "[v]", "-map", "[a]",
            "-t", f"{dur:.3f}",
            "-c:v", v["codec"], "-preset", v["preset"], "-crf", str(v["crf"]),
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(rcfg["fps"]),
            "-c:a", "aac", "-b:a", rcfg["audio"]["bitrate"], "-ar", str(rcfg["audio"]["sample_rate"]),
            "-movflags", "+faststart", str(out)]
    return cmd


# --- public API -----------------------------------------------------------------------------

def render_candidate(cand_id: int, preset_name: str, cfg: dict, db) -> dict:
    cand = db.get_candidate(cand_id)
    if cand is None:
        raise KeyError(f"no candidate #{cand_id}")
    media = db.get_media(cand["media_id"])
    preset = cfg["render"]["presets"][preset_name]
    rcfg = cfg["render"]
    out_dir = workspace(cfg) / "renders" / str(media["id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"cand{cand_id}_{preset_name}"
    out = out_dir / f"{stem}.mp4"
    start, dur = cand["start_s"], cand["duration_s"]

    with stage(db, f"render:{preset_name}", media["id"], {"candidate_id": cand_id}) as detail:
        t0 = time.perf_counter()
        srt_name = None
        srt = sidecar_srt(media["path"]) if rcfg["subtitles"]["enabled"] else None
        if srt:
            text = shift_srt(parse_srt(srt.read_text(errors="replace")), start, start + dur)
            if text.strip():
                (out_dir / f"{stem}.srt").write_text(text)
                srt_name = f"{stem}.srt"   # relative: ffmpeg runs with cwd=out_dir (no escaping issues)
        loud = measure_loudness(media["path"], start, dur, rcfg["loudness"]) if media["has_audio"] else None
        cmd = build_command(media["path"], out.name, start, dur, preset, rcfg,
                            bool(media["has_audio"]), loud, srt_name)
        cmd[-1] = str(out)
        proc = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
        if proc.returncode != 0:
            raise ffmpeg.FFmpegError(f"render failed: {proc.stderr.strip()[-800:]}")
        thumb = out_dir / f"{stem}.jpg"
        peak_rel = min(max(cand["peak_s"] - start, 0.1), max(dur - 0.1, 0.1))
        ffmpeg.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{peak_rel:.3f}", "-i", str(out),
                    "-frames:v", "1", "-vf", "scale=-2:360", "-q:v", "3", str(thumb)])
        render_s = round(time.perf_counter() - t0, 3)
        try:
            meta = ffmpeg.probe(out)
        except ffmpeg.FFmpegError:
            meta = {"width": None, "height": None, "duration_s": None}
        detail.update(preset=preset_name, render_s=render_s, clip_s=dur,
                      realtime_x=round(dur / render_s, 2) if render_s else None,
                      subtitles=bool(srt_name), loudnorm=bool(loud))
        rid = db.upsert_render(candidate_id=cand_id, preset=preset_name, path=str(out),
                               thumb_path=str(thumb) if thumb.exists() else None,
                               width=meta["width"], height=meta["height"], duration_s=meta["duration_s"],
                               size_bytes=out.stat().st_size, render_s=render_s)
    return next(r for r in db.renders(cand_id) if r["id"] == rid)


def render_all_presets(cand_id: int, cfg: dict, db, presets: list[str] | None = None) -> list[dict]:
    names = presets or list(cfg["render"]["presets"])
    return [render_candidate(cand_id, n, cfg, db) for n in names]
