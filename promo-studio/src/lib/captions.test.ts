import { test } from 'node:test';
import assert from 'node:assert/strict';
import { activeWordIndex, buildPages, pageAt, type CaptionWord } from './captions.ts';

const opts = { maxChars: 22, maxWords: 3, maxGapSeconds: 0.45 };
const w = (text: string, start: number, end: number, extra: Partial<CaptionWord> = {}): CaptionWord => ({
  text,
  start,
  end,
  ...extra,
});

test('splits on max words', () => {
  const pages = buildPages([w('a', 0, 0.1), w('b', 0.1, 0.2), w('c', 0.2, 0.3), w('d', 0.3, 0.4)], opts);
  assert.deepEqual(
    pages.map((p) => p.words.map((x) => x.text)),
    [['a', 'b', 'c'], ['d']],
  );
});

test('splits after sentence punctuation and on long pauses', () => {
  const pages = buildPages([w('Hi.', 0, 0.2), w('Your', 0.3, 0.5), w('site', 1.2, 1.4)], opts);
  assert.deepEqual(
    pages.map((p) => p.words.map((x) => x.text)),
    [['Hi.'], ['Your'], ['site']],
  );
});

test('splits on character budget and forced breaks', () => {
  const pages = buildPages(
    [w('extraordinarily', 0, 0.5), w('beautiful', 0.5, 0.9), w('now', 0.9, 1), w('go', 1, 1.1, { break: true })],
    opts,
  );
  assert.deepEqual(
    pages.map((p) => p.words.map((x) => x.text)),
    [['extraordinarily'], ['beautiful', 'now'], ['go']],
  );
});

test('page holds until next page or hold limit', () => {
  const pages = buildPages([w('one.', 0, 0.3), w('two', 0.5, 0.7)], opts);
  assert.equal(pages[0].end, 0.5);
  assert.ok(Math.abs(pages[1].end - 1.3) < 1e-9);
});

test('active word and page lookup', () => {
  const pages = buildPages([w('a', 0, 0.2), w('b', 0.25, 0.4)], opts);
  assert.equal(activeWordIndex(pages[0], 0.1), 0);
  assert.equal(activeWordIndex(pages[0], 0.22), 0);
  assert.equal(activeWordIndex(pages[0], 0.3), 1);
  assert.equal(pageAt(pages, 5), null);
});
