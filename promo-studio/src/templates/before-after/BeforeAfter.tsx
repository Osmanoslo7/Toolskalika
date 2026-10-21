import React from 'react';
import { AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig } from 'remotion';
import { theme } from '../../theme';
import { Callout } from '../../shared/Callout';
import { EndCard } from '../../shared/EndCard';
import { FontGate } from '../../shared/FontGate';
import { HoldVideo } from '../../shared/HoldVideo';
import { HookHeadline } from '../../shared/HookHeadline';
import { KineticCaptions } from '../../shared/KineticCaptions';
import { LogoSting } from '../../shared/LogoSting';
import { PhoneMockup, phoneDims } from '../../shared/PhoneMockup';
import { Backdrop, SafeZones } from '../../shared/Stage';
import { TalkingHeadBubble } from '../../shared/TalkingHeadBubble';
import { WipeSlider, wipePosition } from '../../shared/WipeSlider';
import type { BeforeAfterProps } from './schema';

// Layout for 1080x1920, kept clear of the TikTok/Reels right rail and bottom text.
const L = {
  hook: { top: 165, width: 960 },
  phone: { screenWidth: 440, right: 958, top: 452 },
  bubble: { diameter: 400, x: 58, y: 490 },
  callouts: { left: theme.safe.side, top: 942, step: 104, maxWidth: 420 },
  captions: { centerY: 1528, width: 980 },
};

const screenVideoStyle: React.CSSProperties = {
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  objectPosition: '50% 0%',
};

const Main: React.FC<BeforeAfterProps> = (p) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const phone = phoneDims(L.phone.screenWidth);
  const phoneX = L.phone.right - phone.outerWidth;
  const position = wipePosition(frame / fps, p.wipe);
  const wipeFrame = Math.round(p.wipe.at * fps);

  return (
    <AbsoluteFill>
      <Backdrop glowX={phoneX + phone.outerWidth / 2} glowY={L.phone.top + phone.outerHeight / 2} />
      <HookHeadline text={p.hook} top={L.hook.top} width={L.hook.width} />

      <PhoneMockup screenWidth={L.phone.screenWidth} x={phoneX} y={L.phone.top}>
        <WipeSlider
          position={position}
          width={phone.screenWidth}
          height={phone.screenHeight}
          beforeLabel={p.before.label}
          afterLabel={p.after.label}
          before={<HoldVideo src={p.before.src} durationSec={p.before.durationSec} muted style={screenVideoStyle} />}
          after={
            <Sequence from={wipeFrame}>
              <HoldVideo src={p.after.src} durationSec={p.after.durationSec} muted style={screenVideoStyle} />
            </Sequence>
          }
        />
      </PhoneMockup>

      {p.callouts.map((c, i) => (
        <Callout
          key={`${c.text}-${i}`}
          text={c.text}
          icon={c.icon}
          enterFrame={Math.round(c.at * fps)}
          exitFrame={c.until === null ? null : Math.round(c.until * fps)}
          left={L.callouts.left}
          top={L.callouts.top + i * L.callouts.step}
          maxWidth={L.callouts.maxWidth}
        />
      ))}

      <TalkingHeadBubble
        src={p.talkingHead.src}
        durationSec={p.talkingHead.durationSec}
        focusY={p.talkingHead.focusY}
        diameter={L.bubble.diameter}
        x={L.bubble.x}
        y={L.bubble.y}
      />
      <KineticCaptions words={p.captions} centerY={L.captions.centerY} width={L.captions.width} />
      <LogoSting mascotHead={p.mascot.head} />
    </AbsoluteFill>
  );
};

export const BeforeAfter: React.FC<BeforeAfterProps> = (props) => {
  const { fps } = useVideoConfig();
  const mainFrames = Math.round(props.talkingHead.durationSec * fps);
  const endFrames = Math.round(props.endCard.seconds * fps);
  return (
    <AbsoluteFill style={{ background: theme.colors.bg }}>
      <FontGate>
        <Sequence durationInFrames={mainFrames + theme.timing.endCardFadeFrames}>
          <Main {...props} />
        </Sequence>
        <Sequence from={mainFrames} durationInFrames={endFrames}>
          <EndCard title={props.endCard.title} subtitle={props.endCard.subtitle} mascot={props.mascot.full} />
        </Sequence>
        {props.showSafeZones && <SafeZones />}
      </FontGate>
    </AbsoluteFill>
  );
};
