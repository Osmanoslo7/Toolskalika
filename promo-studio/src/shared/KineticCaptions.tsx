import React, { useMemo } from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { activeWordIndex, buildPages, pageAt, type CaptionWord } from '../lib/captions';
import { theme } from '../theme';

const displayText = (text: string) => text.replace(/[.,;:]+$/, '');

export const KineticCaptions: React.FC<{
  words: CaptionWord[];
  centerY: number;
  width: number;
  fontSize?: number;
}> = ({ words, centerY, width, fontSize = theme.captions.fontSize }) => {
  const frame = useCurrentFrame();
  const { fps, width: canvasWidth } = useVideoConfig();
  const pages = useMemo(
    () =>
      buildPages(words, {
        maxChars: theme.captions.maxCharsPerPage,
        maxWords: theme.captions.maxWordsPerPage,
        maxGapSeconds: theme.captions.maxGapSeconds,
      }),
    [words],
  );

  const t = frame / fps;
  const page = pageAt(pages, t);
  if (!page) return null;

  const pop = spring({
    frame: frame - Math.round(page.start * fps),
    fps,
    config: { damping: 14, stiffness: 240, mass: 0.6 },
  });
  const active = activeWordIndex(page, t);

  return (
    <div
      style={{
        position: 'absolute',
        left: (canvasWidth - width) / 2,
        width,
        top: centerY,
        transform: `translateY(-50%) scale(${interpolate(pop, [0, 1], [0.86, 1])})`,
        opacity: Math.min(1, pop * 1.6),
        textAlign: 'center',
        fontFamily: theme.fonts.heavy,
        fontWeight: 900,
        fontSize,
        lineHeight: 1.08,
        textTransform: 'uppercase',
        letterSpacing: '-0.01em',
      }}
    >
      {page.words.map((word, i) => {
        const isActive = i === active;
        const wordPop = isActive
          ? spring({
              frame: frame - Math.round(word.start * fps),
              fps,
              config: { damping: 12, stiffness: 320, mass: 0.5 },
            })
          : 0;
        const gold = isActive || word.emphasis;
        return (
          <span
            key={`${word.start}-${i}`}
            style={{
              display: 'inline-block',
              margin: '0 0.2em', // room for the active word's 1.1x pop
              color: gold ? theme.colors.gold : theme.colors.silver,
              transform: `scale(${isActive ? interpolate(wordPop, [0, 1], [1, 1.1]) : 1})`,
              WebkitTextStroke: '12px #000',
              paintOrder: 'stroke fill',
              textShadow: isActive
                ? '0 0 28px rgba(251,193,70,0.55), 0 8px 18px rgba(0,0,0,0.7)'
                : '0 8px 18px rgba(0,0,0,0.7)',
            }}
          >
            {displayText(word.text)}
          </span>
        );
      })}
    </div>
  );
};
