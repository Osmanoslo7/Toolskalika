// Parses the JSON block ffmpeg's loudnorm filter prints in its first pass.
export type LoudnormMeasure = {
  input_i: string;
  input_tp: string;
  input_lra: string;
  input_thresh: string;
  target_offset: string;
};

export const parseLoudnorm = (stderr: string): LoudnormMeasure => {
  const start = stderr.lastIndexOf('{');
  const end = stderr.lastIndexOf('}');
  if (start < 0 || end < start) throw new Error('loudnorm did not print a measurement (is there an audio track?)');
  const json = JSON.parse(stderr.slice(start, end + 1)) as LoudnormMeasure;
  for (const k of ['input_i', 'input_tp', 'input_lra', 'input_thresh', 'target_offset'] as const) {
    if (!Number.isFinite(Number(json[k]))) throw new Error(`loudnorm measurement has invalid ${k}: ${json[k]}`);
  }
  return json;
};

// TP is aimed at -2.0 so the AAC encode's inter-sample overshoot still lands under -1.5 dBTP.
export const LOUDNESS_TARGET = { I: -14, TP: -2.0, LRA: 11 };
export const TRUE_PEAK_CEILING = -1.5;

export const secondPassFilter = (m: LoudnormMeasure) =>
  `loudnorm=I=${LOUDNESS_TARGET.I}:TP=${LOUDNESS_TARGET.TP}:LRA=${LOUDNESS_TARGET.LRA}` +
  `:measured_I=${m.input_i}:measured_TP=${m.input_tp}:measured_LRA=${m.input_lra}` +
  `:measured_thresh=${m.input_thresh}:offset=${m.target_offset}:linear=true:print_format=summary`;

// Parses silencedetect output into [start, end] ranges (end = null if silence runs to EOF).
export const parseSilences = (stderr: string): Array<{ start: number; end: number | null }> => {
  const out: Array<{ start: number; end: number | null }> = [];
  for (const line of stderr.split('\n')) {
    const s = line.match(/silence_start: (-?[\d.]+)/);
    if (s) out.push({ start: Math.max(0, Number(s[1])), end: null });
    const e = line.match(/silence_end: ([\d.]+)/);
    if (e && out.length && out[out.length - 1].end === null) out[out.length - 1].end = Number(e[1]);
  }
  return out;
};

// Trims dead air so speech (the hook) starts almost immediately.
export const autoTrim = (
  silences: Array<{ start: number; end: number | null }>,
  duration: number,
  lead = 0.12,
  tail = 0.35,
): { start: number; end: number } => {
  let start = 0;
  let end = duration;
  const first = silences[0];
  if (first && first.start <= 0.05 && first.end !== null) start = Math.max(0, first.end - lead);
  const last = silences[silences.length - 1];
  if (last && (last.end === null || last.end >= duration - 0.05) && last.start > start) {
    end = Math.min(duration, last.start + tail);
  }
  return { start, end };
};
