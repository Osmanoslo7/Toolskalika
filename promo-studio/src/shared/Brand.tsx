import React from 'react';
import { Img, staticFile } from 'remotion';
import { theme } from '../theme';

export const goldText = (sheenAt: number | null = null): React.CSSProperties => ({
  backgroundImage:
    sheenAt === null
      ? theme.gradients.gold
      : `linear-gradient(100deg, transparent 38%, rgba(255,255,255,0.9) 50%, transparent 62%), ${theme.gradients.gold}`,
  backgroundSize: sheenAt === null ? '100% 100%' : '260% 100%, 100% 100%',
  backgroundPosition: sheenAt === null ? '0 0' : `${sheenAt}% 0, 0 0`,
  backgroundRepeat: 'no-repeat',
  WebkitBackgroundClip: 'text',
  backgroundClip: 'text',
  color: 'transparent',
});

export const silverText: React.CSSProperties = {
  backgroundImage: theme.gradients.silver,
  WebkitBackgroundClip: 'text',
  backgroundClip: 'text',
  color: 'transparent',
};

// Round badge with the mascot's head, or an "IH" monogram if no image is set.
export const MascotBadge: React.FC<{ size: number; src: string | null }> = ({ size, src }) => (
  <div
    style={{
      width: size,
      height: size,
      borderRadius: '50%',
      padding: Math.max(3, size * 0.045),
      background: theme.gradients.goldEdge,
      boxShadow: `0 0 ${size * 0.4}px rgba(230,143,30,0.45)`,
      flexShrink: 0,
    }}
  >
    <div
      style={{
        width: '100%',
        height: '100%',
        borderRadius: '50%',
        overflow: 'hidden',
        background: theme.colors.bg,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {src ? (
        <Img src={staticFile(src)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      ) : (
        <span style={{ fontFamily: theme.fonts.display, fontSize: size * 0.42, ...goldText() }}>IH</span>
      )}
    </div>
  </div>
);

export const Wordmark: React.FC<{ size: number; sheenAt?: number | null }> = ({ size, sheenAt = null }) => (
  <div style={{ lineHeight: 1 }}>
    <div
      style={{
        fontFamily: theme.fonts.tracked,
        fontWeight: 700,
        fontSize: size,
        letterSpacing: '0.3em',
        ...goldText(sheenAt),
      }}
    >
      {theme.brandName}
    </div>
    <div
      style={{
        fontFamily: theme.fonts.tracked,
        fontWeight: 600,
        fontSize: size * 0.48,
        letterSpacing: '0.62em',
        color: theme.colors.silverMid,
        marginTop: size * 0.14,
      }}
    >
      {theme.brandSub}
    </div>
  </div>
);
