import type { CaptionWord } from '../../src/lib/captions.ts';

export type AutoWord = { text: string; start: number; end: number };

const norm = (s: string) => s.toLowerCase().replace(/[^\p{L}\p{N}']+/gu, '');
const trailingPunct = (s: string) => s.match(/[^\p{L}\p{N}]+$/u)?.[0] ?? '';

// Applies `corrections` ({"iron hand": "Ironhand"}) to a word list. Multi-word
// keys merge consecutive words into one, keeping the first start and last end.
// `locked[i] = true` marks words the user edited; those are never touched.
export const applyCorrections = (
  words: CaptionWord[],
  corrections: Record<string, string>,
  locked: boolean[] = [],
): CaptionWord[] => {
  const rules = Object.entries(corrections)
    .map(([from, to]) => ({ tokens: from.split(/\s+/).map(norm).filter(Boolean), to }))
    .filter((r) => r.tokens.length > 0)
    .sort((a, b) => b.tokens.length - a.tokens.length);

  const out: CaptionWord[] = [];
  let i = 0;
  while (i < words.length) {
    const rule = rules.find(
      (r) =>
        i + r.tokens.length <= words.length &&
        r.tokens.every((tok, k) => !locked[i + k] && norm(words[i + k].text) === tok),
    );
    if (!rule) {
      out.push(words[i]);
      i += 1;
      continue;
    }
    const first = words[i];
    const last = words[i + rule.tokens.length - 1];
    out.push({ ...first, text: rule.to + trailingPunct(last.text), end: last.end });
    i += rule.tokens.length;
  }
  return out;
};

// A word in captions.json counts as "yours" (edited) unless it is identical to a
// Whisper word at the same time. Only untouched words get automatic corrections.
export const mergeCaptions = (
  edited: CaptionWord[],
  auto: AutoWord[],
  corrections: Record<string, string>,
): CaptionWord[] => {
  const autoKeys = new Set(auto.map((w) => `${w.text}@${w.start.toFixed(2)}`));
  const locked = edited.map(
    (w) => !autoKeys.has(`${w.text}@${w.start.toFixed(2)}`) || w.emphasis !== undefined || w.break !== undefined,
  );
  return applyCorrections(edited, corrections, locked);
};
