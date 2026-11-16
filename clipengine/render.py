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


def zoom_filter(zooms: list[float], amount: float, w: int, h: int) -> str:
    """Brief punch-in at each time: +amount scale that decays over ~0.4 s, centre-anchored."""
    terms = "+".join(f"between(t,{t:.3f},{t + 0.45:.3f})*exp(-(t-{t:.3f})*7)" for t in zooms)
    z = f"(1+{amount}*({terms}))"
    return f"scale=w='trunc({w}*{z}/2)*2':h='trunc({h}*{z}/2)*2':eval=frame,crop={w}:{h}"


def plan_effects(cand: dict, profile: dict, ecfg: dict, sfx_reg: dict, dur: float) -> dict:
    """Choose subtle effects from the clip's sound events. Returns {"sfx": [...], "zooms": [...]}."""
    rules = profile.get("enhance", {})
    sfx_on, zoom_on = set(rules.get("impact_sfx_on", [])), set(rules.get("zoom_on", []))
    picked, zooms, last = [], [], -9.0
    events = sorted(cand["reasons"].get("events", []), key=lambda e: -e["confidence"])
    for e in events:
        t = e.get("t_clip", 0.0)
        if e["confidence"] < ecfg["min_confidence"] or not 0.3 <= t <= dur - 0.5:
            continue
        if any(abs(t - x["t"]) < 1.5 for x in picked) or len(picked) >= ecfg["max_effects"]:
            continue
        kind = e["type"]
        confirmed_hit = kind in ("impact", "explosion", "gunfire") and e.get("confirmed")
        want_sfx = kind in sfx_on
        want_zoom = kind in zoom_on or (confirmed_hit and "confirmed_hit" in zoom_on)
        if not (want_sfx or want_zoom):
            continue
        entry = {"t": round(t, 3), "event": kind}
        if want_sfx:
            name = "impact_low" if kind == "explosion" else "impact_soft"
            entry.update(sfx=name, path=sfx_reg[name]["path"], license=sfx_reg[name]["license"])
        if want_zoom:
            zooms.append(round(t, 3))
        picked.append(entry)
        last = t
    return {"sfx": [p for p in picked if "sfx" in p], "zooms": sorted(zooms)}


def build_command(src: str, out: Path, start: float, dur: float, preset: dict, rcfg: dict,
                  has_audio: bool, loud: dict | None, srt_name: str | None,
                  effects: dict | None = None) -> list[str]:
    w, h = preset["width"], preset["height"]
    fi = min(rcfg["fade_in_s"], dur / 3)
    fo = min(rcfg["fade_out_s"], dur / 3)
    vf = video_filter(preset["mode"], w, h) + f",fps={rcfg['fps']}"
    effects = effects or {"sfx": [], "zooms": []}
    if effects["zooms"]:
        vf += "," + zoom_filter(effects["zooms"], rcfg["enhance"]["zoom"], w, h)
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
    sr = rcfg["audio"]["sample_rate"]
    af += f",aresample={sr},aformat=channel_layouts=stereo"
    tail = ""
    if fi > 0:
        tail += f"afade=t=in:st=0:d={fi:.3f},"
    if fo > 0:
        tail += f"afade=t=out:st={dur - fo:.3f}:d={fo:.3f},"
    tail += "anull"

    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src]
    if not has_audio:  # keep every output consistent: always a (silent) stereo track
        cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", f"anullsrc=r={sr}:cl=stereo"]
    a_in = "0:a:0" if has_audio else "1:a:0"
    graph = f"[0:v:0]{vf}[v];[{a_in}]{af}[am]"
    first_sfx = 2 if not has_audio else 1
    sfx = effects["sfx"]
    for k, e in enumerate(sfx):
        cmd += ["-i", e["path"]]
        ms = int(e["t"] * 1000)
        gain = rcfg["enhance"]["sfx_gain_db"]
        graph += (f";[{first_sfx + k}:a]aresample={sr},aformat=channel_layouts=stereo,"
                  f"adelay={ms}|{ms},volume={gain}dB[s{k}]")
    if sfx:
        mix_in = "[am]" + "".join(f"[s{k}]" for k in range(len(sfx)))
        graph += f";{mix_in}amix=inputs={len(sfx) + 1}:normalize=0:duration=first,{tail}[a]"
    else:
        graph += f";[am]{tail}[a]"
    v = rcfg["video"]
    cmd += ["-filter_complex", graph, "-map", "[v]", "-map", "[a]",
            "-t", f"{dur:.3f}",
            "-c:v", v["codec"], "-preset", v["preset"], "-crf", str(v["crf"]),
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(rcfg["fps"]),
            "-c:a", "aac", "-b:a", rcfg["audio"]["bitrate"], "-ar", str(rcfg["audio"]["sample_rate"]),
            "-movflags", "+faststart", str(out)]
    return cmd


# --- public API -----------------------------------------------------------------------------

def render_candidate(cand_id: int, preset_name: str, cfg: dict, db, enhance: bool | None = None) -> dict:
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
        enhance = rcfg["enhance"]["enabled"] if enhance is None else enhance
        effects = {"sfx": [], "zooms": []}
        if enhance:
            from .intelligence.profiles import load_profile
            from .intelligence.sfx import ensure_builtin
            effects = plan_effects(cand, load_profile(media.get("game")), rcfg["enhance"],
                                   ensure_builtin(cfg), dur)
        # Every sound in the output, with its licence, for the export licence gate.
        audio_sources = [{"name": "source recording", "license": "user-recording",
                          "path": media["path"]}] if media["has_audio"] else []
        audio_sources += [{"name": e["sfx"], "license": e["license"], "path": e["path"], "t": e["t"]}
                          for e in effects["sfx"]]
        cmd = build_command(media["path"], out.name, start, dur, preset, rcfg,
                            bool(media["has_audio"]), loud, srt_name, effects)
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
                      subtitles=bool(srt_name), loudnorm=bool(loud), effects=effects)
        rid = db.upsert_render(candidate_id=cand_id, preset=preset_name, path=str(out),
                               audio_json=audio_sources, enhanced=int(bool(effects["sfx"] or effects["zooms"])),
                               thumb_path=str(thumb) if thumb.exists() else None,
                               width=meta["width"], height=meta["height"], duration_s=meta["duration_s"],
                               size_bytes=out.stat().st_size, render_s=render_s)
    return next(r for r in db.renders(cand_id) if r["id"] == rid)


def render_all_presets(cand_id: int, cfg: dict, db, presets: list[str] | None = None,
                       enhance: bool | None = None) -> list[dict]:
    names = presets or list(cfg["render"]["presets"])
    return [render_candidate(cand_id, n, cfg, db, enhance) for n in names]
