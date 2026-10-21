import React, { useMemo } from 'react';
import { fitTextOnNLines } from '@remotion/layout-utils';
import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { theme } from '../theme';
import { goldText, MascotBadge, Wordmark } from './Brand';
import { ArrowIcon } from './Icons';

export const EndCard: React.FC<{ title: string; subtitle: string; mascot: string | null }> = ({
  title,
  subtitle,
  mascot,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const t = frame / fps;
  const { fontSize, lines } = useMemo(
    () =>
      fitTextOnNLines({
        text: title.toUpperCase(),
        maxLines: 2,
        maxBoxWidth: 920,
        fontFamily: theme.fonts.display,
        maxFontSize: 200,
      }),
    [title],
  );

  const fadeFrames = theme.timing.endCardFadeFrames;
  const enter = interpolate(frame, [0, fadeFrames], [0, 1], { extrapolateRight: 'clamp' });
  const zoom = interpolate(frame, [0, 10], [1.06, 1], { extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  const sheen = interpolate(frame, [6, 40], [130, -30], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const float = Math.sin((t * Math.PI * 2) / 2.2) * 12;
  const glow = 0.45 + 0.25 * Math.sin((t * Math.PI * 2) / 1.6);
  const arrow = Math.sin((t * Math.PI * 2) / 0.9) * 10;
  const mascotIn = interpolate(frame, [2, 12], [80, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.4)) });
  const raysTurn = interpolate(frame, [0, durationInFrames], [0, 18]);

  return (
    <AbsoluteFill style={{ opacity: enter, transform: `scale(${zoom})` }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at 50% 36%, rgba(230,143,30,0.38) 0%, rgba(230,143,30,0.08) 38%, transparent 60%), ${theme.colors.bg}`,
        }}
      />
      <AbsoluteFill
        style={{
          background: `repeating-conic-gradient(from ${raysTurn}deg at 50% 36%, rgba(251,193,70,0.07) 0deg 6deg, transparent 6deg 18deg)`,
          maskImage: 'radial-gradient(circle at 50% 36%, black 0%, transparent 62%)',
          WebkitMaskImage: 'radial-gradient(circle at 50% 36%, black 0%, transparent 62%)',
        }}
      />

      <div style={{ position: 'absolute', top: 250, left: (width - 920) / 2, width: 920, textAlign: 'center' }}>
        <div
          style={{
            fontFamily: theme.fonts.display,
            fontSize,
            lineHeight: 0.98,
            filter: 'drop-shadow(0 8px 0 rgba(0,0,0,0.7)) drop-shadow(0 0 36px rgba(230,143,30,0.35))',
          }}
        >
          {lines.map((line, i) => (
            <div key={i} style={goldText(sheen)}>
              {line}
            </div>
          ))}
        </div>
        <div
          style={{
            marginTop: 34,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 20,
            padding: '18px 40px',
            borderRadius: 999,
            background: theme.gradients.gold,
            boxShadow: '0 14px 40px rgba(0,0,0,0.6), 0 0 40px rgba(251,193,70,0.35)',
          }}
        >
          <div style={{ transform: `translateX(${arrow}px)` }}>
            <ArrowIcon size={56} color={theme.colors.ink} />
          </div>
          <span style={{ fontFamily: theme.fonts.heavy, fontWeight: 900, fontSize: 58, color: theme.colors.ink }}>
            {subtitle}
          </span>
        </div>
        <div style={{ marginTop: 44, display: 'flex', justifyContent: 'center' }}>
          <Wordmark size={40} />
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 0,
          height: height * 0.5,
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'center',
          transform: `translateY(${mascotIn + float}px)`,
        }}
      >
        {mascot ? (
          <Img
            src={staticFile(mascot)}
            style={{
              height: '100%',
              objectFit: 'contain',
              filter: `drop-shadow(0 0 ${40 + glow * 40}px rgba(251,193,70,${glow}))`,
            }}
          />
        ) : (
          <div style={{ marginBottom: 220 }}>
            <MascotBadge size={320} src={null} />
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
