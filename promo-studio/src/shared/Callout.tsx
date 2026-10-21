import React, { useMemo } from 'react';
import { fitText } from '@remotion/layout-utils';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { theme } from '../theme';
import { CalloutIcon, type IconName } from './Icons';

const ICON = 54;
const GAP = 16;
const PAD_LEFT = 12;
const PAD_RIGHT = 26;

export const Callout: React.FC<{
  text: string;
  icon: IconName;
  enterFrame: number;
  exitFrame: number | null;
  left: number;
  top: number;
  maxWidth: number;
}> = ({ text, icon, enterFrame, exitFrame, left, top, maxWidth }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fontSize = useMemo(() => {
    const room = maxWidth - PAD_LEFT - PAD_RIGHT - (icon === 'none' ? 0 : ICON + GAP);
    return Math.min(42, fitText({ text, withinWidth: room, fontFamily: theme.fonts.heavy, fontWeight: 800 }).fontSize);
  }, [text, icon, maxWidth]);

  const rel = frame - enterFrame;
  if (rel < 0 || (exitFrame !== null && frame >= exitFrame)) return null;

  const s = spring({ frame: rel, fps, config: { damping: 14, stiffness: 230, mass: 0.7 } });
  const iconPop = spring({ frame: rel - 3, fps, config: { damping: 10, stiffness: 300, mass: 0.5 } });
  const out =
    exitFrame === null
      ? 1
      : interpolate(frame, [exitFrame - 6, exitFrame], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const shine = interpolate(rel, [4, 20], [-40, 140], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  return (
    <div
      style={{
        position: 'absolute',
        left,
        top,
        opacity: Math.min(1, s * 1.5) * out,
        transform: `translateX(${interpolate(s, [0, 1], [-70, 0])}px) scale(${interpolate(s, [0, 1], [0.85, 1])})`,
        transformOrigin: 'left center',
      }}
    >
      <div
        style={{
          position: 'relative',
          overflow: 'hidden',
          display: 'inline-flex',
          alignItems: 'center',
          gap: GAP,
          padding: `12px ${PAD_RIGHT}px 12px ${PAD_LEFT}px`,
          borderRadius: 999,
          background: 'rgba(35,33,28,0.94)',
          border: '2px solid rgba(251,193,70,0.75)',
          boxShadow: '0 12px 40px rgba(0,0,0,0.55), 0 0 26px rgba(230,143,30,0.25)',
        }}
      >
        {icon !== 'none' && (
          <div
            style={{
              width: ICON,
              height: ICON,
              borderRadius: '50%',
              background: theme.gradients.gold,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transform: `scale(${interpolate(iconPop, [0, 1], [0.4, 1])})`,
              flexShrink: 0,
            }}
          >
            <CalloutIcon name={icon} size={ICON * 0.62} color={theme.colors.ink} />
          </div>
        )}
        <span
          style={{
            fontFamily: theme.fonts.heavy,
            fontWeight: 800,
            fontSize,
            color: theme.colors.silver,
            whiteSpace: 'nowrap',
          }}
        >
          {text}
        </span>
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: `linear-gradient(100deg, transparent ${shine - 20}%, rgba(253,243,160,0.35) ${shine}%, transparent ${shine + 20}%)`,
            pointerEvents: 'none',
          }}
        />
      </div>
    </div>
  );
};
