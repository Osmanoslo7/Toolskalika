import React from 'react';
import { theme } from '../theme';

export const phoneDims = (screenWidth: number) => {
  const screenHeight = Math.round(screenWidth * 2.1667);
  const bezel = Math.round(screenWidth * 0.034);
  return {
    screenWidth,
    screenHeight,
    bezel,
    outerWidth: screenWidth + bezel * 2,
    outerHeight: screenHeight + bezel * 2,
    radius: Math.round(screenWidth * 0.155),
  };
};

export const PhoneMockup: React.FC<{
  screenWidth: number;
  x: number;
  y: number;
  children: React.ReactNode;
}> = ({ screenWidth, x, y, children }) => {
  const d = phoneDims(screenWidth);
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        width: d.outerWidth,
        height: d.outerHeight,
        borderRadius: d.radius + d.bezel,
        padding: 3,
        boxSizing: 'border-box',
        background: theme.gradients.goldEdge,
        boxShadow: '0 50px 120px rgba(0,0,0,0.75), 0 0 90px rgba(230,143,30,0.28)',
      }}
    >
      <div
        style={{
          width: '100%',
          height: '100%',
          borderRadius: d.radius + d.bezel - 3,
          background: '#0b0a08',
          padding: d.bezel - 3,
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            position: 'relative',
            width: d.screenWidth,
            height: d.screenHeight,
            borderRadius: d.radius,
            overflow: 'hidden',
            background: '#000',
          }}
        >
          {children}
          <div
            style={{
              position: 'absolute',
              top: Math.round(screenWidth * 0.032),
              left: '50%',
              transform: 'translateX(-50%)',
              width: Math.round(screenWidth * 0.3),
              height: Math.round(screenWidth * 0.085),
              borderRadius: 999,
              background: '#000',
            }}
          />
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'linear-gradient(115deg, rgba(255,255,255,0.07) 0%, transparent 38%)',
              pointerEvents: 'none',
            }}
          />
        </div>
      </div>
    </div>
  );
};
