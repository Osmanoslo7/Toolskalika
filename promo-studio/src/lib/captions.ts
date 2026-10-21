export type CaptionWord = {
  text: string;
  start: number;
  end: number;
  emphasis?: boolean;
  break?: boolean;
};

export type CaptionPage = {
  words: CaptionWord[];
  start: number;
  // When the page leaves the screen. Short silences keep the page up to avoid flicker.
  end: number;
};

export type PagingOptions = {
  maxChars: number;
  maxWords: number;
  maxGapSeconds: number;
  holdAfterSeconds?: number;
};

const endsSentence = (text: string) => /[.!?,;:]["')\]]?$/.test(text);

export const buildPages = (words: CaptionWord[], opts: PagingOptions): CaptionPage[] => {
  const hold = opts.holdAfterSeconds ?? 0.6;
  const groups: CaptionWord[][] = [];
  let current: CaptionWord[] = [];

  for (const word of words) {
    const prev = current[current.length - 1];
    const chars = current.reduce((n, w) => n + w.text.length + 1, 0) + word.text.length;
    const startNew =
      current.length > 0 &&
      (word.break ||
        current.length >= opts.maxWords ||
        chars > opts.maxChars ||
        word.start - prev.end > opts.maxGapSeconds ||
        endsSentence(prev.text));
    if (startNew) {
      groups.push(current);
      current = [];
    }
    current.push(word);
  }
  if (current.length) groups.push(current);

  return groups.map((group, i) => {
    const start = group[0].start;
    const lastEnd = group[group.length - 1].end;
    const next = groups[i + 1];
    const end = next ? Math.min(next[0].start, lastEnd + hold) : lastEnd + hold;
    return { words: group, start, end: Math.max(end, lastEnd) };
  });
};

// A word stays highlighted until the next word starts, so the highlight never blinks off mid-page.
export const activeWordIndex = (page: CaptionPage, t: number): number => {
  for (let i = page.words.length - 1; i >= 0; i--) {
    if (t >= page.words[i].start) return i;
  }
  return -1;
};

export const pageAt = (pages: CaptionPage[], t: number): CaptionPage | null =>
  pages.find((p) => t >= p.start && t < p.end) ?? null;
