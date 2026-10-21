import { z } from 'zod';

// Fully resolved render props. `npm run props` builds these from project.json,
// so every time is already in seconds and every path is relative to the public dir.

export const captionWordSchema = z.object({
  text: z.string(),
  start: z.number(),
  end: z.number(),
  emphasis: z.boolean().optional(),
  break: z.boolean().optional(),
});

export const mediaSchema = z.object({
  src: z.string(),
  durationSec: z.number().positive(),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
});

export const calloutSchema = z.object({
  text: z.string(),
  icon: z.enum(['check', 'bolt', 'none']),
  at: z.number().nonnegative(),
  until: z.number().nullable(),
});

export const beforeAfterSchema = z.object({
  durationInFrames: z.number().int().positive(),
  hook: z.string(),
  talkingHead: mediaSchema.extend({ focusY: z.number().min(0).max(1) }),
  before: mediaSchema.extend({ label: z.string() }),
  after: mediaSchema.extend({ label: z.string() }),
  wipe: z.object({ at: z.number(), sweep: z.number().positive(), peekHold: z.number().nonnegative() }),
  callouts: z.array(calloutSchema),
  captions: z.array(captionWordSchema),
  endCard: z.object({ title: z.string(), subtitle: z.string(), seconds: z.number().positive() }),
  mascot: z.object({ full: z.string().nullable(), head: z.string().nullable() }),
  showSafeZones: z.boolean(),
});

export type BeforeAfterProps = z.infer<typeof beforeAfterSchema>;

export const beforeAfterDefaults: BeforeAfterProps = {
  durationInFrames: 450,
  hook: 'Your website is losing customers',
  talkingHead: { src: 'media/talking-head.mp4', durationSec: 12.5, width: 1080, height: 1920, focusY: 0.38 },
  before: { src: 'media/before.mp4', durationSec: 8, width: 780, height: 1688, label: 'BEFORE' },
  after: { src: 'media/after.mp4', durationSec: 8, width: 780, height: 1688, label: 'AFTER' },
  wipe: { at: 3, sweep: 1.6, peekHold: 1 },
  callouts: [],
  captions: [],
  endCard: { title: 'Free website audit', subtitle: 'link in bio', seconds: 2.5 },
  mascot: { full: null, head: null },
  showSafeZones: false,
};
