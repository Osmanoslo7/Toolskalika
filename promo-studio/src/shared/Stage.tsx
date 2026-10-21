import React from 'react';
import { AbsoluteFill } from 'remotion';
import { theme } from '../theme';

// Dark brand backdrop with a warm glow behind the hero area.
export const Backdrop: React.FC<{ glowX: number; glowY: number }> = ({ glowX, glowY }) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(circle at ${glowX}px ${glowY}px, rgba(230,143,30,0.30) 0%, rgba(230,143,30,0.06) 30%, transparent 52%),
        radial-gradient(ellipse at 50% 120%, rgba(230,143,30,0.16) 0%, transparent 55%),
        ${theme.colors.bg}`,
    }}
  >
    <AbsoluteFill style={{ boxShadow: 'inset 0 0 220px rgba(0,0,0,0.85)' }} />
  </AbsoluteFill>
);

// Toggle with "showSafeZones": shows where TikTok/Reels UI will cover the frame.
export const SafeZones: React.FC = () => {
  const s = theme.safe;
  const zone: React.CSSProperties = {
    position: 'absolute',
    background: 'rgba(255,0,60,0.28)',
    border: '2px dashed rgba(255,0,60,0.9)',
    boxSizing: 'border-box',
  };
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div style={{ ...zone, left: 0, top: 0, width: 1080, height: s.top }} />
      <div style={{ ...zone, left: 0, top: s.bottom, width: 1080, height: 1920 - s.bottom }} />
      <div style={{ ...zone, left: s.rightRailX, top: s.rightRailTop, width: 1080 - s.rightRailX, height: s.bottom - s.rightRailTop }} />
    </AbsoluteFill>
  );
};
