import React from 'react';

// Drawn icons instead of emoji, so callouts look identical on every machine.
export const CheckIcon: React.FC<{ size: number; color: string }> = ({ size, color }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path d="M4.5 12.5l4.8 4.8L19.5 7" stroke={color} strokeWidth={3.4} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const BoltIcon: React.FC<{ size: number; color: string }> = ({ size, color }) => (
  <svg width={size} height={size} viewBox="0 0 24 24">
    <path d="M13.6 2.2L4.8 13.4h6l-1.4 8.4 8.8-11.2h-6l1.4-8.4z" fill={color} />
  </svg>
);

export const ArrowIcon: React.FC<{ size: number; color: string }> = ({ size, color }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path d="M3 12h16M13 5.5L19.5 12 13 18.5" stroke={color} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export type IconName = 'check' | 'bolt' | 'none';

export const CalloutIcon: React.FC<{ name: IconName; size: number; color: string }> = ({ name, size, color }) =>
  name === 'check' ? <CheckIcon size={size} color={color} /> : name === 'bolt' ? <BoltIcon size={size} color={color} /> : null;
