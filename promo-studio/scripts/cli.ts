import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';
import type { CaptionWord } from '../src/lib/captions.ts';
import { beforeAfterSchema, type BeforeAfterProps } from '../src/templates/before-after/schema.ts';
import { theme } from '../src/theme.ts';
import { applyCorrections, mergeCaptions, type AutoWord } from './lib/captions-merge.ts';
import { autoTrim, LOUDNESS_TARGET, parseLoudnorm, parseSilences, secondPassFilter } from './lib/loudness.ts';
import {
  beforeAfterProjectSchema,
  compositionIds,
  formatZodError,
  parseCalloutText,
  type BeforeAfterProject,
} from './lib/project.ts';
import { resolveTime } from './lib/timeref.ts';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const FFMPEG = process.env.FFMPEG_PATH ?? 'ffmpeg';
const FFPROBE = process.env.FFPROBE_PATH ?? 'ffprobe';
const FPS = theme.video.fps;
const IS_WIN = process.platform === 'win32';

class UserError extends Error {}

const c = {
  bold: (s: string) => `\x1b[1m${s}\x1b[0m`,
  yellow: (s: string) => `\x1b[33m${s}\x1b[0m`,
  red: (s: string) => `\x1b[31m${s}\x1b[0m`,
  green: (s: string) => `\x1b[32m${s}\x1b[0m`,
  dim: (s: string) => `\x1b[2m${s}\x1b[0m`,
};
const step = (s: string) => console.log(`\n${c.bold('▸ ' + s)}`);
const warnings: string[] = [];
const warn = (s: string) => {
  warnings.push(s);
  console.log(c.yellow(`  ⚠ ${s}`));
};

const projectPaths = (name: string) => {
  const dir = path.join(ROOT, 'projects', name);
  const build = path.join(dir, 'build');
  const pub = path.join(build, 'public');
  return {
    dir,
    build,
    pub,
    media: path.join(pub, 'media'),
    projectJson: path.join(dir, 'project.json'),
    notes: path.join(dir, 'notes.md'),
    captions: path.join(dir, 'captions.json'),
    captionsAuto: path.join(dir, 'captions.auto.json'),
    wav: path.join(build, 'talking-head-16k.wav'),
    meta: path.join(build, 'meta.json'),
    props: path.join(build, 'props.json'),
    render: path.join(build, 'render.mp4'),
    out: path.join(dir, 'out', `${name}.mp4`),
  };
};
type Paths = ReturnType<typeof projectPaths>;

const run = (cmd: string, args: string[], opts: { capture?: boolean; cwd?: string } = {}) => {
  const r = spawnSync(cmd, args, {
    encoding: 'utf8',
    cwd: opts.cwd,
    stdio: opts.capture ? ['ignore', 'pipe', 'pipe'] : 'inherit',
    maxBuffer: 1 << 28,
    shell: IS_WIN && cmd.endsWith('.cmd'),
  });
  if (r.error) {
    const hint = (r.error as NodeJS.ErrnoException).code === 'ENOENT' ? ' (is it installed and on your PATH?)' : '';
    throw new UserError(`Could not run ${cmd}${hint}: ${r.error.message}`);
  }
  if (r.status !== 0) {
    const tail = opts.capture ? `\n${(r.stderr || '').slice(-2500)}` : '';
    throw new UserError(`${path.basename(cmd)} failed with exit code ${r.status}${tail}`);
  }
  return r;
};

const readJson = <T>(file: string): T | null => (fs.existsSync(file) ? (JSON.parse(fs.readFileSync(file, 'utf8')) as T) : null);
const writeJson = (file: string, data: unknown) => {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + '\n');
};
const sha1File = (file: string) => createHash('sha1').update(fs.readFileSync(file)).digest('hex');
const rel = (file: string) => path.relative(process.cwd(), file) || '.';

const loadProject = (p: Paths): BeforeAfterProject => {
  const raw = readJson<unknown>(p.projectJson);
  if (!raw) throw new UserError(`No project at ${rel(p.projectJson)}. Create one with: npm run new -- <name>`);
  const result = beforeAfterProjectSchema.safeParse(raw);
  if (!result.success) throw new UserError(formatZodError(rel(p.projectJson), result.error));
  return result.data;
};

// ---------- probing ----------

type Probe = { duration: number; width: number; height: number; hasAudio: boolean; hdr: boolean };

const probe = (file: string): Probe => {
  const r = run(FFPROBE, ['-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', file], { capture: true });
  const j = JSON.parse(r.stdout) as {
    format: { duration?: string };
    streams: Array<{
      codec_type: string;
      width?: number;
      height?: number;
      color_transfer?: string;
      tags?: { rotate?: string };
      side_data_list?: Array<{ rotation?: number }>;
    }>;
  };
  const v = j.streams.find((s) => s.codec_type === 'video');
  if (!v || !v.width || !v.height) throw new UserError(`${rel(file)} has no video stream`);
  const rotation = Number(v.side_data_list?.find((d) => d.rotation !== undefined)?.rotation ?? v.tags?.rotate ?? 0);
  const sideways = Math.abs(rotation) % 180 === 90;
  return {
    duration: Number(j.format.duration ?? 0),
    width: sideways ? v.height : v.width,
    height: sideways ? v.width : v.height,
    hasAudio: j.streams.some((s) => s.codec_type === 'audio'),
    hdr: ['smpte2084', 'arib-std-b67'].includes(v.color_transfer ?? ''),
  };
};

// iPhone HDR (HLG / Dolby Vision) looks washed out unless tone-mapped to SDR.
const toneMap = (hdr: boolean) =>
  hdr
    ? 'zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,'
    : '';

const inputSignature = (file: string, settings: unknown) => {
  const st = fs.statSync(file);
  return `${st.size}:${Math.round(st.mtimeMs)}:${JSON.stringify(settings)}`;
};

// ---------- staging the public dir ----------

// Shared assets (fonts, brand) are hard-linked next to this project's media so
// Remotion gets one public dir per project without copying gigabytes around.
const stagePublic = (pub: string) => {
  const src = path.join(ROOT, 'public');
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const from = path.join(dir, entry.name);
      const to = path.join(pub, path.relative(src, from));
      if (entry.isDirectory()) {
        fs.mkdirSync(to, { recursive: true });
        walk(from);
        continue;
      }
      if (fs.existsSync(to)) {
        if (fs.statSync(to).ino === fs.statSync(from).ino) continue;
        fs.rmSync(to);
      }
      try {
        fs.linkSync(from, to);
      } catch {
        fs.copyFileSync(from, to);
      }
    }
  };
  fs.mkdirSync(pub, { recursive: true });
  walk(src);
};

// ---------- prep ----------

type MediaMeta = { src: string; durationSec: number; width: number; height: number; sig: string };
type TalkingHeadMeta = MediaMeta & { trimStart: number; trimEnd: number };
type Meta = { talkingHead?: TalkingHeadMeta; before?: MediaMeta; after?: MediaMeta };

const resolveInput = (p: Paths, file: string, field: string) => {
  const abs = path.resolve(p.dir, file);
  if (!fs.existsSync(abs)) throw new UserError(`${field}: file not found: ${rel(abs)}`);
  return abs;
};

const prepTalkingHead = (p: Paths, project: BeforeAfterProject, prev: Meta, force: boolean): TalkingHeadMeta => {
  const cfg = project.talkingHead;
  const src = resolveInput(p, cfg.file, 'talkingHead.file');
  const out = path.join(p.media, 'talking-head.mp4');
  const sig = inputSignature(src, { cfg, silenceDb: project.silenceDb });
  if (!force && prev.talkingHead?.sig === sig && fs.existsSync(out) && fs.existsSync(p.wav)) {
    console.log(c.dim('  talking head unchanged, skipping'));
    return prev.talkingHead;
  }

  const info = probe(src);
  if (!info.hasAudio) throw new UserError('talkingHead.file has no audio track — captions and voice need it.');
  if (info.width > info.height) warn('Talking head is landscape; it will be center-cropped to vertical.');

  let start = typeof cfg.trimStart === 'number' ? cfg.trimStart : 0;
  let end = typeof cfg.trimEnd === 'number' ? cfg.trimEnd : info.duration;
  if (cfg.trimStart === 'auto' || cfg.trimEnd === 'auto') {
    const r = run(
      FFMPEG,
      ['-hide_banner', '-nostats', '-i', src, '-vn', '-af', `silencedetect=noise=${project.silenceDb}dB:d=0.35`, '-f', 'null', '-'],
      { capture: true },
    );
    const auto = autoTrim(parseSilences(r.stderr), info.duration);
    if (cfg.trimStart === 'auto') start = auto.start;
    if (cfg.trimEnd === 'auto') end = auto.end;
    console.log(c.dim(`  auto-trim: ${start.toFixed(2)}s → ${end.toFixed(2)}s (of ${info.duration.toFixed(2)}s)`));
  }
  if (end - start < 1) throw new UserError(`talkingHead trim leaves ${(end - start).toFixed(2)}s — check trimStart/trimEnd.`);
  if (info.hdr) console.log(c.dim('  HDR source detected, tone-mapping to SDR'));

  fs.mkdirSync(p.media, { recursive: true });
  run(FFMPEG, [
    '-hide_banner', '-loglevel', 'error', '-stats', '-y',
    '-ss', start.toFixed(3), '-to', end.toFixed(3), '-i', src,
    '-map', '0:v:0', '-map', '0:a:0',
    '-vf', `${toneMap(info.hdr)}scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,fps=${FPS},format=yuv420p,setsar=1`,
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-profile:v', 'high',
    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
    '-movflags', '+faststart', out,
  ]);
  run(FFMPEG, ['-hide_banner', '-loglevel', 'error', '-y', '-i', out, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', p.wav]);
  const done = probe(out);
  return { src: 'media/talking-head.mp4', durationSec: done.duration, width: 1080, height: 1920, trimStart: start, trimEnd: end, sig };
};

const prepScreen = (
  p: Paths,
  kind: 'before' | 'after',
  cfg: BeforeAfterProject['before'],
  prev: Meta,
  force: boolean,
): MediaMeta => {
  const src = resolveInput(p, cfg.file, `${kind}.file`);
  const out = path.join(p.media, `${kind}.mp4`);
  const sig = inputSignature(src, cfg);
  const old = prev[kind];
  if (!force && old?.sig === sig && fs.existsSync(out)) {
    console.log(c.dim(`  ${kind} recording unchanged, skipping`));
    return old;
  }
  const info = probe(src);
  if (info.width / info.height > 0.75) {
    warn(
      `${kind}: this looks like a desktop recording (${info.width}x${info.height}). The phone mockup shows its top, ` +
        'cropped to phone shape. Record the mobile view (phone screen recorder or Chrome DevTools device mode) for best results.',
    );
  }
  const trim: string[] = [];
  if (typeof cfg.trimStart === 'number' && cfg.trimStart > 0) trim.push('-ss', cfg.trimStart.toFixed(3));
  if (typeof cfg.trimEnd === 'number') trim.push('-to', cfg.trimEnd.toFixed(3));
  run(FFMPEG, [
    '-hide_banner', '-loglevel', 'error', '-stats', '-y', ...trim, '-i', src,
    '-map', '0:v:0', '-an',
    '-vf', `${toneMap(info.hdr)}scale='trunc(min(1080,iw)/2)*2':-2:flags=lanczos,fps=${FPS},format=yuv420p,setsar=1`,
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-movflags', '+faststart', out,
  ]);
  const done = probe(out);
  return { src: `media/${kind}.mp4`, durationSec: done.duration, width: done.width, height: done.height, sig };
};

const prep = (name: string, force: boolean) => {
  const p = projectPaths(name);
  const project = loadProject(p);
  step(`Prep ${name}`);
  stagePublic(p.pub);
  const prev = readJson<Meta>(p.meta) ?? {};
  const meta: Meta = { ...prev };
  meta.talkingHead = prepTalkingHead(p, project, prev, force);
  meta.before = prepScreen(p, 'before', project.before, prev, force);
  meta.after = prepScreen(p, 'after', project.after, prev, force);
  writeJson(p.meta, meta);
  console.log(c.green(`  ✓ media ready (talking head ${meta.talkingHead.durationSec.toFixed(2)}s)`));
};

// ---------- transcribe ----------

type CaptionsFile = { _help?: string; audioHash?: string; words: CaptionWord[] };
type AutoFile = { audioHash: string; words: Array<AutoWord & { probability?: number }> };

const CAPTIONS_HELP =
  'Your captions. Fix words, delete fillers, add "emphasis": true (always gold) or "break": true (start a new caption). ' +
  'Re-running transcribe never overwrites this file; delete it (or use --reset) to start over.';

const findPython = () => {
  if (process.env.IRONHAND_PYTHON) return process.env.IRONHAND_PYTHON;
  const venv = path.join(ROOT, '.venv', IS_WIN ? 'Scripts/python.exe' : 'bin/python');
  return fs.existsSync(venv) ? venv : IS_WIN ? 'python' : 'python3';
};

const whisperPrompt = (project: BeforeAfterProject, notesFile: string) => {
  const notes = fs.existsSync(notesFile)
    ? fs.readFileSync(notesFile, 'utf8').replace(/[#*>_`|-]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 400)
    : '';
  return [project.captions.vocabulary.join(', '), notes].filter(Boolean).join('. ');
};

const transcribe = (name: string, reset: boolean) => {
  const p = projectPaths(name);
  const project = loadProject(p);
  step(`Transcribe ${name} (faster-whisper ${project.captions.model}, local)`);
  if (!fs.existsSync(p.wav)) throw new UserError('No prepped audio yet. Run: npm run prep -- ' + name);
  run(findPython(), [
    path.join(ROOT, 'scripts', 'transcribe.py'),
    '--audio', p.wav,
    '--out', p.captionsAuto,
    '--model', project.captions.model,
    '--language', project.captions.language,
    '--prompt', whisperPrompt(project, p.notes),
  ]);
  const auto = readJson<AutoFile>(p.captionsAuto)!;
  const existing = readJson<CaptionsFile>(p.captions);
  if (!existing || reset) {
    const words = applyCorrections(
      auto.words.map(({ text, start, end }) => ({ text, start, end })),
      project.captions.corrections,
    );
    writeJson(p.captions, { _help: CAPTIONS_HELP, audioHash: auto.audioHash, words } satisfies CaptionsFile);
    console.log(c.green(`  ✓ wrote ${rel(p.captions)} (${words.length} words) — edit it freely`));
  } else if (existing.audioHash && existing.audioHash !== auto.audioHash) {
    warn(
      `${rel(p.captions)} was made from a different recording. Your edits were kept, but timings may be wrong. ` +
        `Run "npm run transcribe -- ${name} --reset" to start fresh.`,
    );
  } else {
    console.log(c.dim(`  kept your ${rel(p.captions)} (updated ${rel(p.captionsAuto)} only)`));
  }
};

// ---------- props ----------

const maxOverlap = (items: Array<{ at: number; until: number | null }>, end: number) => {
  let best = 0;
  for (const a of items) {
    const n = items.filter((b) => b.at <= a.at && (b.until ?? end) > a.at).length;
    best = Math.max(best, n);
  }
  return best;
};

const buildProps = (name: string): BeforeAfterProps => {
  const p = projectPaths(name);
  const project = loadProject(p);
  step(`Build props for ${name}`);
  const meta = readJson<Meta>(p.meta);
  if (!meta?.talkingHead || !meta.before || !meta.after) throw new UserError('Media not prepped yet. Run: npm run prep -- ' + name);
  stagePublic(p.pub);

  const captionsFile = readJson<CaptionsFile>(p.captions);
  if (!captionsFile) {
    throw new UserError(
      `No ${rel(p.captions)}. Run "npm run transcribe -- ${name}" (or write it by hand: {"words":[{"text":"Hi","start":0,"end":0.3}]}).`,
    );
  }
  const auto = readJson<AutoFile>(p.captionsAuto);
  const duration = meta.talkingHead.durationSec;
  const words = mergeCaptions(captionsFile.words, auto?.words ?? [], project.captions.corrections)
    .map((w) => ({ ...w, end: Math.max(w.end, w.start + 0.05) }))
    .sort((a, b) => a.start - b.start);
  const late = words.filter((w) => w.start >= duration);
  if (late.length) warn(`${late.length} caption word(s) start after the talking head ends and will not show.`);

  const at = (ref: number | string, field: string) => resolveTime(ref, words, field);
  const callouts = project.callouts.map((co, i) => {
    const parsed = parseCalloutText(co.text, co.icon);
    const start = at(co.at, `callouts[${i}].at`);
    const until = co.until === null ? null : at(co.until, `callouts[${i}].until`);
    if (start >= duration) warn(`Callout "${parsed.text}" starts after you stop talking (${start.toFixed(2)}s).`);
    if (until !== null && until <= start) throw new UserError(`callouts[${i}]: "until" must be after "at".`);
    return { ...parsed, at: start, until };
  });
  if (maxOverlap(callouts, duration) > 3) warn('More than 3 callouts on screen at once; the 4th will overlap your talking head.');

  const wipe = { at: at(project.wipe.at, 'wipe.at'), sweep: project.wipe.sweep, peekHold: project.wipe.peekHold };
  if (wipe.at + wipe.sweep + wipe.peekHold > duration) warn('The before/after wipe finishes after you stop talking.');
  if (words.length && words[0].start > 1) warn(`Your first word starts at ${words[0].start.toFixed(2)}s — the hook should land in the first second.`);
  if (project.hook.length > 48) warn('Hook text is long; it will shrink to fit two lines. Aim for under ~40 characters.');

  const asset = (file: string | null) => {
    if (!file) return null;
    if (fs.existsSync(path.join(p.pub, file))) return file;
    warn(`Mascot image public/${file} not found; using the monogram instead.`);
    return null;
  };

  const props: BeforeAfterProps = {
    durationInFrames: Math.round(duration * FPS) + Math.round(project.endCard.seconds * FPS),
    hook: project.hook,
    talkingHead: { ...pickMedia(meta.talkingHead), focusY: project.talkingHead.focusY },
    before: { ...pickMedia(meta.before), label: project.before.label },
    after: { ...pickMedia(meta.after), label: project.after.label },
    wipe,
    callouts,
    captions: words,
    endCard: project.endCard,
    mascot: { full: asset(project.mascot.full), head: asset(project.mascot.head) },
    showSafeZones: project.showSafeZones,
  };
  const valid = beforeAfterSchema.safeParse(props);
  if (!valid.success) throw new UserError(formatZodError('render props', valid.error));
  writeJson(p.props, valid.data);
  console.log(
    c.green(
      `  ✓ ${rel(p.props)}: ${(props.durationInFrames / FPS).toFixed(2)}s, ${words.length} caption words, ` +
        `wipe at ${wipe.at.toFixed(2)}s, ${callouts.length} callouts`,
    ),
  );
  return valid.data;
};

const pickMedia = (m: MediaMeta) => ({ src: m.src, durationSec: m.durationSec, width: m.width, height: m.height });

// ---------- render ----------

const remotionBin = () => path.join(ROOT, 'node_modules', '.bin', IS_WIN ? 'remotion.cmd' : 'remotion');

const verify = (file: string) => {
  const s = JSON.parse(
    run(FFPROBE, ['-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', file], { capture: true }).stdout,
  ) as { streams: Array<Record<string, string | number>>; format: { duration: string } };
  const v = s.streams.find((x) => x.codec_type === 'video')!;
  const a = s.streams.find((x) => x.codec_type === 'audio');
  const ebur = run(FFMPEG, ['-hide_banner', '-nostats', '-i', file, '-filter_complex', 'ebur128=peak=true', '-f', 'null', '-'], {
    capture: true,
  }).stderr;
  const summary = ebur.slice(ebur.lastIndexOf('Summary:'));
  const lufs = summary.match(/I:\s+(-?[\d.]+) LUFS/)?.[1];
  const peak = summary.match(/Peak:\s+(-?[\d.]+) dBFS/)?.[1];
  console.log(
    `  video: ${v.codec_name} ${v.profile} ${v.width}x${v.height} @ ${v.r_frame_rate} ${v.pix_fmt}\n` +
      `  audio: ${a ? `${a.codec_name} ${a.sample_rate} Hz` : 'none'}\n` +
      `  loudness: ${lufs} LUFS integrated (target ${LOUDNESS_TARGET.I}), true peak ${peak} dBFS (ceiling ${LOUDNESS_TARGET.TP})\n` +
      `  duration: ${Number(s.format.duration).toFixed(2)}s`,
  );
};

const render = (name: string) => {
  const p = projectPaths(name);
  const project = loadProject(p);
  buildProps(name);
  step(`Render ${name} with Remotion`);
  run(
    remotionBin(),
    ['render', 'src/index.ts', compositionIds[project.template], p.render, `--props=${p.props}`, `--public-dir=${p.pub}`],
    { cwd: ROOT },
  );

  step('Normalize loudness (two-pass EBU R128)');
  const target = `loudnorm=I=${LOUDNESS_TARGET.I}:TP=${LOUDNESS_TARGET.TP}:LRA=${LOUDNESS_TARGET.LRA}:print_format=json`;
  const measured = parseLoudnorm(
    run(FFMPEG, ['-hide_banner', '-nostats', '-i', p.render, '-map', '0:a:0', '-af', target, '-f', 'null', '-'], { capture: true }).stderr,
  );
  console.log(c.dim(`  measured ${measured.input_i} LUFS, true peak ${measured.input_tp} dBTP`));
  fs.mkdirSync(path.dirname(p.out), { recursive: true });
  run(FFMPEG, [
    '-hide_banner', '-loglevel', 'error', '-y', '-i', p.render,
    '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'copy',
    '-af', secondPassFilter(measured), '-ar', '48000', '-c:a', 'aac', '-b:a', '192k',
    '-movflags', '+faststart', p.out,
  ]);

  step('Check output');
  verify(p.out);
  console.log(c.green(`\n✓ Done: ${rel(p.out)}`));
};

const preview = (name: string) => {
  const p = projectPaths(name);
  buildProps(name);
  step('Opening Remotion Studio (Ctrl+C to stop)');
  run(remotionBin(), ['studio', 'src/index.ts', `--props=${p.props}`, `--public-dir=${p.pub}`], { cwd: ROOT });
};

// ---------- new ----------

const createProject = (name: string, template: string) => {
  if (!/^[a-z0-9][a-z0-9_-]*$/i.test(name)) throw new UserError('Project names use letters, numbers, - and _ only.');
  const starter = path.join(ROOT, 'scripts', 'starter', template);
  if (!fs.existsSync(starter)) throw new UserError(`Unknown template "${template}". Available: before-after`);
  const p = projectPaths(name);
  if (fs.existsSync(p.dir)) throw new UserError(`${rel(p.dir)} already exists.`);
  fs.mkdirSync(path.join(p.dir, 'raw'), { recursive: true });
  for (const f of fs.readdirSync(starter)) fs.copyFileSync(path.join(starter, f), path.join(p.dir, f));
  console.log(
    c.green(`✓ Created ${rel(p.dir)}`) +
      `\n  1. Put your clips in ${rel(path.join(p.dir, 'raw'))}/ (talking-head.mp4, old-site.mp4, new-site.mp4)` +
      `\n  2. Edit ${rel(p.projectJson)} (hook, callouts) and ${rel(p.notes)} (your script)` +
      `\n  3. npm run make -- ${name}`,
  );
};

// ---------- main ----------

const USAGE = `Ironhand Promo Studio

  npm run new -- <name> [before-after]   create projects/<name>
  npm run prep -- <name> [--force]       normalize footage with FFmpeg
  npm run transcribe -- <name> [--reset] captions with local faster-whisper
  npm run props -- <name>                validate project.json + captions
  npm run preview -- <name>              open Remotion Studio with your footage
  npm run render -- <name>               render + loudness-normalize to out/<name>.mp4
  npm run make -- <name>                 prep + transcribe (if needed) + render`;

const main = () => {
  const [cmd, name, ...rest] = process.argv.slice(2);
  const flags = new Set(rest.filter((r) => r.startsWith('--')));
  if (!cmd || !name || cmd === 'help') {
    console.log(USAGE);
    process.exit(cmd ? 0 : 1);
  }
  switch (cmd) {
    case 'new':
      return createProject(name, rest.find((r) => !r.startsWith('--')) ?? 'before-after');
    case 'prep':
      return prep(name, flags.has('--force'));
    case 'transcribe':
      return transcribe(name, flags.has('--reset'));
    case 'props':
      return void buildProps(name);
    case 'preview':
      return preview(name);
    case 'render':
      return render(name);
    case 'make': {
      prep(name, flags.has('--force'));
      if (!fs.existsSync(projectPaths(name).captions)) transcribe(name, false);
      else console.log(c.dim(`\n  using existing captions.json (run "npm run transcribe -- ${name}" to refresh)`));
      return render(name);
    }
    default:
      console.log(USAGE);
      process.exit(1);
  }
};

try {
  main();
  if (warnings.length) console.log(c.yellow(`\n${warnings.length} warning(s) above — worth a look.`));
} catch (e) {
  if (e instanceof UserError || e instanceof z.ZodError) {
    console.error(c.red(`\n✗ ${e.message}`));
    process.exit(1);
  }
  throw e;
}
