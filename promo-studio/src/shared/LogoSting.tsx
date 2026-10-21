import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { theme } from '../theme';
import { MascotBadge, Wordmark } from './Brand';

// A small corner flash over the hook. It never sits in front of the footage.
export const LogoSting: React.FC<{ mascotHead: string | null }> = ({ mascotHead }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = theme.timing.logoStingFrames;
  if (frame >= total) return null;

  const enter = spring({ frame, fps, config: { damping: 16, stiffness: 280, mass: 0.6 } });
  const exit = interpolate(frame, [total - 6, total], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const sheen = interpolate(frame, [2, total - 4], [130, -30], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  return (
    <div
      style={{
        position: 'absolute',
        left: theme.safe.side,
        top: 52,
        display: 'flex',
        alignItems: 'center',
        gap: 18,
        opacity: Math.min(1, enter * 1.5) * exit,
        transform: `translateX(${interpolate(enter, [0, 1], [-60, 0])}px)`,
      }}
    >
      <MascotBadge size={92} src={mascotHead} />
      <Wordmark size={38} sheenAt={sheen} />
    </div>
  );
};
