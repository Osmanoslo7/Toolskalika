import type { CaptionWord } from '../../src/lib/captions.ts';

// A time in project.json is either seconds (4.2) or a spoken-word anchor:
//   "@after"       start of the first time you say "after"
//   "@after#2"     the second time
//   "@after+0.3"   0.3s after it starts (also -0.2)
// Anchors keep animations in sync when you re-record.
export type TimeRef = number | string;

const norm = (s: string) => s.toLowerCase().replace(/[^\p{L}\p{N}']+/gu, '');

export const resolveTime = (ref: TimeRef, words: CaptionWord[], field: string): number => {
  if (typeof ref === 'number') return ref;
  const m = ref.match(/^@([^#+\-]+?)(?:#(\d+))?(?:([+-]\d+(?:\.\d+)?))?$/);
  if (!m) throw new Error(`${field}: "${ref}" is not a number or an anchor like "@word", "@word#2", "@word+0.3"`);
  const target = norm(m[1]);
  const nth = m[2] ? Number(m[2]) : 1;
  const offset = m[3] ? Number(m[3]) : 0;
  const hits = words.filter((w) => norm(w.text) === target);
  if (hits.length < nth) {
    const said = words.map((w) => w.text).join(' ');
    throw new Error(
      `${field}: "${ref}" — "${m[1]}" is said ${hits.length} time(s), needed occurrence #${nth}.\nCaptions: ${said}`,
    );
  }
  return Math.max(0, hits[nth - 1].start + offset);
};
