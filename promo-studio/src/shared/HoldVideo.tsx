import React from 'react';
import { Freeze, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';

// Plays a clip, then holds its last frame (muted) instead of disappearing.
export const HoldVideo: React.FC<{
  src: string;
  durationSec: number;
  muted?: boolean;
  style?: React.CSSProperties;
}> = ({ src, durationSec, muted = false, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const last = Math.max(0, Math.floor(durationSec * fps) - 2);
  const holding = frame > last;
  const video = <OffthreadVideo src={staticFile(src)} muted={muted || holding} style={style} />;
  return holding ? <Freeze frame={last}>{video}</Freeze> : video;
};
