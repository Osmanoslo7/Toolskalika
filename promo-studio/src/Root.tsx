import React from 'react';
import { Composition } from 'remotion';
import { theme } from './theme';
import { BeforeAfter } from './templates/before-after/BeforeAfter';
import { beforeAfterDefaults, beforeAfterSchema } from './templates/before-after/schema';

export const Root: React.FC = () => (
  <>
    <Composition
      id="BeforeAfter"
      component={BeforeAfter}
      width={theme.video.width}
      height={theme.video.height}
      fps={theme.video.fps}
      durationInFrames={beforeAfterDefaults.durationInFrames}
      schema={beforeAfterSchema}
      defaultProps={beforeAfterDefaults}
      calculateMetadata={({ props }) => ({ durationInFrames: props.durationInFrames })}
    />
  </>
);
