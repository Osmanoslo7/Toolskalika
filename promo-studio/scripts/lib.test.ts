import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyCorrections, mergeCaptions } from './lib/captions-merge.ts';
import { resolveTime } from './lib/timeref.ts';
import { autoTrim, parseLoudnorm, parseSilences, secondPassFilter } from './lib/loudness.ts';

const w = (text: string, start: number, end: number) => ({ text, start, end });

test('multi-word correction merges words and keeps punctuation and timing', () => {
  const out = applyCorrections([w('Iron', 1, 1.2), w('hand,', 1.2, 1.5), w('hi', 2, 2.1)], { 'iron hand': 'Ironhand' });
  assert.deepEqual(out, [w('Ironhand,', 1, 1.5), w('hi', 2, 2.1)]);
});

test('single-word correction is case-insensitive', () => {
  const out = applyCorrections([w('whatsapp', 0, 0.4)], { WhatsApp: 'WhatsApp' });
  assert.equal(out[0].text, 'WhatsApp');
});

test('your edits win: edited words never get auto-corrected', () => {
  const auto = [w('iron', 0, 0.2), w('hand', 0.2, 0.4), w('whats', 1, 1.2), w('app', 1.2, 1.4)];
  // You re-spelled the first pair yourself as "IRON hand" (a deliberate choice).
  const edited = [w('IRON', 0, 0.2), w('hand', 0.2, 0.4), w('whats', 1, 1.2), w('app', 1.2, 1.4)];
  const out = mergeCaptions(edited, auto, { 'iron hand': 'Ironhand', 'whats app': 'WhatsApp' });
  assert.deepEqual(
    out.map((x) => x.text),
    ['IRON', 'hand', 'WhatsApp'],
  );
});

test('deleted filler words stay deleted', () => {
  const auto = [w('um', 0, 0.2), w('hello', 0.3, 0.6)];
  const out = mergeCaptions([w('hello', 0.3, 0.6)], auto, {});
  assert.deepEqual(out.map((x) => x.text), ['hello']);
});

test('time anchors', () => {
  const words = [w('Before:', 1, 1.3), w('after', 2, 2.2), w('After!', 5, 5.3)];
  assert.equal(resolveTime(4.2, words, 'x'), 4.2);
  assert.equal(resolveTime('@after', words, 'x'), 2);
  assert.equal(resolveTime('@after#2', words, 'x'), 5);
  assert.equal(resolveTime('@before+0.5', words, 'x'), 1.5);
  assert.equal(resolveTime('@after-3', words, 'x'), 0);
  assert.throws(() => resolveTime('@missing', words, 'wipe.at'), /said 0 time/);
  assert.throws(() => resolveTime('soon', words, 'wipe.at'), /not a number/);
});

test('loudnorm parsing and second pass', () => {
  const stderr = `[Parsed_loudnorm_0 @ 0x1]\n{\n\t"input_i" : "-23.10",\n\t"input_tp" : "-4.20",\n\t"input_lra" : "6.00",\n\t"input_thresh" : "-33.50",\n\t"output_i" : "-14.0",\n\t"target_offset" : "0.30"\n}\n`;
  const m = parseLoudnorm(stderr);
  assert.equal(m.input_i, '-23.10');
  assert.match(secondPassFilter(m), /measured_I=-23.10:measured_TP=-4.20.*linear=true/);
  assert.throws(() => parseLoudnorm('no json'), /did not print/);
});

test('silence parsing and auto trim', () => {
  const stderr = [
    '[silencedetect @ 0x1] silence_start: -0.02',
    '[silencedetect @ 0x1] silence_end: 1.4 | silence_duration: 1.42',
    '[silencedetect @ 0x1] silence_start: 5.0',
    '[silencedetect @ 0x1] silence_end: 5.6 | silence_duration: 0.6',
    '[silencedetect @ 0x1] silence_start: 9.1',
  ].join('\n');
  const s = parseSilences(stderr);
  assert.deepEqual(s, [
    { start: 0, end: 1.4 },
    { start: 5, end: 5.6 },
    { start: 9.1, end: null },
  ]);
  const t = autoTrim(s, 10);
  assert.ok(Math.abs(t.start - 1.28) < 1e-9);
  assert.ok(Math.abs(t.end - 9.45) < 1e-9);
  assert.deepEqual(autoTrim([], 7), { start: 0, end: 7 });
});
