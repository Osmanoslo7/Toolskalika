import React from 'react';
import { AbsoluteFill, Easing, interpolate } from 'remotion';
import { theme } from '../theme';

export type WipeTiming = { at: number; sweep: number; peekHold: number };

// 1 = all BEFORE, 0 = all AFTER. Sweeps to half, holds for a side-by-side look, then finishes.
export const wipePosition = (t: number, w: WipeTiming): number => {
  const half = w.sweep / 2;
  const ease = { easing: Easing.inOut(Easing.cubic), extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
  if (t <= w.at) return 1;
  if (t <= w.at + half) return interpolate(t, [w.at, w.at + half], [1, 0.5], ease);
  if (t <= w.at + half + w.peekHold) return 0.5;
  return interpolate(t, [w.at + half + w.peekHold, w.at + w.sweep + w.peekHold], [0.5, 0], ease);
};

const Chip: React.FC<{ label: string; gold: boolean; side: 'left' | 'right'; opacity: number; top: number }> = ({
  label,
  gold,
  side,
  opacity,
  top,
}) => (
  <div
    style={{
      position: 'absolute',
      top,
      [side]: 16,
      opacity,
      padding: '8px 16px',
      borderRadius: 999,
      fontFamily: theme.fonts.tracked,
      fontWeight: 700,
      fontSize: 26,
      letterSpacing: '0.18em',
      color: gold ? theme.colors.ink : theme.colors.silver,
      background: gold ? theme.gradients.gold : 'rgba(9,8,7,0.78)',
      border: gold ? 'none' : '1.5px solid rgba(248,246,244,0.35)',
      boxShadow: '0 6px 20px rgba(0,0,0,0.5)',
    }}
  >
    {label}
  </div>
);

export const WipeSlider: React.FC<{
  position: number;
  width: number;
  height: number;
  before: React.ReactNode;
  after: React.ReactNode;
  beforeLabel: string;
  afterLabel: string;
}> = ({ position, width, height, before, after, beforeLabel, afterLabel }) => {
  const px = position * width;
  const moving = position > 0.002 && position < 0.998;
  const handle = Math.round(width * 0.15);
  const chipTop = Math.round(width * 0.16);
  return (
    <AbsoluteFill>
      <AbsoluteFill>{after}</AbsoluteFill>
      <AbsoluteFill style={{ clipPath: `inset(0 ${width - px}px 0 0)` }}>{before}</AbsoluteFill>
      {moving && (
        <>
          <div
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: px - 2,
              width: 4,
              background: theme.colors.silver,
              boxShadow: `0 0 18px ${theme.colors.gold}, 0 0 4px rgba(0,0,0,0.6)`,
            }}
          />
          <div
            style={{
              position: 'absolute',
              left: px - handle / 2,
              top: height / 2 - handle / 2,
              width: handle,
              height: handle,
              borderRadius: '50%',
              background: theme.gradients.gold,
              boxShadow: '0 8px 24px rgba(0,0,0,0.6), 0 0 0 3px rgba(9,8,7,0.85)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: handle * 0.08,
              color: theme.colors.ink,
              fontFamily: theme.fonts.heavy,
              fontWeight: 900,
              fontSize: handle * 0.42,
              lineHeight: 1,
            }}
          >
            <span>‹</span>
            <span>›</span>
          </div>
        </>
      )}
      <Chip
        label={beforeLabel}
        gold={false}
        side="left"
        top={chipTop}
        opacity={interpolate(position, [0.12, 0.3], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })}
      />
      <Chip
        label={afterLabel}
        gold
        side="right"
        top={chipTop}
        opacity={interpolate(position, [0.7, 0.88], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })}
      />
    </AbsoluteFill>
  );
};
