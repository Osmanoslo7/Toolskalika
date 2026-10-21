import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { theme } from '../theme';
import { HoldVideo } from './HoldVideo';

// Your talking head, cropped to a circle. This video carries the voice track.
export const TalkingHeadBubble: React.FC<{
  src: string;
  durationSec: number;
  diameter: number;
  x: number;
  y: number;
  focusY: number;
}> = ({ src, durationSec, diameter, x, y, focusY }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 15, stiffness: 190, mass: 0.7 } });
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        width: diameter,
        height: diameter,
        borderRadius: '50%',
        padding: 6,
        boxSizing: 'border-box',
        background: theme.gradients.goldEdge,
        boxShadow: '0 24px 60px rgba(0,0,0,0.6), 0 0 40px rgba(230,143,30,0.3)',
        transform: `scale(${interpolate(s, [0, 1], [0.85, 1])})`,
        opacity: interpolate(s, [0, 1], [0.9, 1]),
      }}
    >
      <div style={{ width: '100%', height: '100%', borderRadius: '50%', overflow: 'hidden', background: '#000' }}>
        <HoldVideo
          src={src}
          durationSec={durationSec}
          style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: `50% ${focusY * 100}%` }}
        />
      </div>
    </div>
  );
};
