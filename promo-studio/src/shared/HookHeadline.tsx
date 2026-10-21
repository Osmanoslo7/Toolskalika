import React, { useMemo } from 'react';
import { fitTextOnNLines } from '@remotion/layout-utils';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { theme } from '../theme';
import { goldText, silverText } from './Brand';

// Readable from frame 0 (starts at 85% opacity), settles within ~0.3s.
export const HookHeadline: React.FC<{ text: string; top: number; width: number; maxFontSize?: number }> = ({
  text,
  top,
  width,
  maxFontSize = 132,
}) => {
  const frame = useCurrentFrame();
  const { fps, width: canvasWidth } = useVideoConfig();
  const { fontSize, lines } = useMemo(
    () =>
      fitTextOnNLines({
        text: text.toUpperCase(),
        maxLines: 2,
        maxBoxWidth: width,
        fontFamily: theme.fonts.display,
        maxFontSize,
      }),
    [text, width, maxFontSize],
  );

  return (
    <div
      style={{
        position: 'absolute',
        top,
        left: (canvasWidth - width) / 2,
        width,
        textAlign: 'center',
        fontFamily: theme.fonts.display,
        fontSize,
        lineHeight: 0.98,
        filter: 'drop-shadow(0 6px 0 rgba(0,0,0,0.65)) drop-shadow(0 0 28px rgba(230,143,30,0.3))',
      }}
    >
      {lines.map((line, i) => {
        const s = spring({ frame: frame - i * 2, fps, config: { damping: 18, stiffness: 220, mass: 0.7 } });
        return (
          <div
            key={i}
            style={{
              transform: `translateY(${interpolate(s, [0, 1], [22, 0])}px)`,
              opacity: interpolate(s, [0, 1], [0.85, 1]),
              ...(i % 2 === 0 ? goldText() : silverText),
            }}
          >
            {line}
          </div>
        );
      })}
    </div>
  );
};
