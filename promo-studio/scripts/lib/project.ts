import { z } from 'zod';
import { theme } from '../../src/theme.ts';

// The file you edit per video: projects/<name>/project.json.
// Times accept seconds (4.2) or spoken-word anchors ("@after", "@after#2", "@after+0.3").

const timeRef = z.union([z.number().nonnegative(), z.string().startsWith('@')]);
const trimValue = z.union([z.number().nonnegative(), z.literal('auto')]);

const clip = z.object({
  file: z.string().min(1),
  trimStart: trimValue.default(0),
  trimEnd: z.union([trimValue, z.null()]).default(null),
});

export const beforeAfterProjectSchema = z.object({
  template: z.literal('before-after'),
  hook: z.string().min(1),
  talkingHead: clip.extend({
    trimStart: trimValue.default('auto'),
    trimEnd: z.union([trimValue, z.null()]).default('auto'),
    focusY: z.number().min(0).max(1).default(0.38),
  }),
  before: clip.extend({ label: z.string().default('BEFORE') }),
  after: clip.extend({ label: z.string().default('AFTER') }),
  wipe: z.object({
    at: timeRef,
    sweep: z.number().positive().default(1.6),
    peekHold: z.number().nonnegative().default(1),
  }),
  callouts: z
    .array(
      z.object({
        text: z.string().min(1),
        at: timeRef,
        until: timeRef.nullable().default(null),
        icon: z.enum(['check', 'bolt', 'none']).optional(),
      }),
    )
    .default([]),
  endCard: z
    .object({
      title: z.string().default('Free website audit'),
      subtitle: z.string().default('link in bio'),
      seconds: z.number().positive().default(theme.timing.endCardSeconds),
    })
    .prefault({}),
  captions: z
    .object({
      language: z.string().default('en'),
      model: z.string().default('small.en'),
      vocabulary: z.array(z.string()).default([]),
      corrections: z.record(z.string(), z.string()).default({}),
    })
    .prefault({}),
  mascot: z
    .object({
      full: z.string().nullable().default('brand/mascot.png'),
      head: z.string().nullable().default('brand/mascot-head.png'),
    })
    .prefault({}),
  silenceDb: z.number().max(0).default(-35),
  showSafeZones: z.boolean().default(false),
});

export type BeforeAfterProject = z.infer<typeof beforeAfterProjectSchema>;

export const projectSchemas = {
  'before-after': beforeAfterProjectSchema,
} as const;

export type TemplateName = keyof typeof projectSchemas;

export const compositionIds: Record<TemplateName, string> = {
  'before-after': 'BeforeAfter',
};

// "Mobile ✓" -> { text: "Mobile", icon: "check" }; "Fast ⚡" -> bolt.
export const parseCalloutText = (
  text: string,
  explicit?: 'check' | 'bolt' | 'none',
): { text: string; icon: 'check' | 'bolt' | 'none' } => {
  const trimmed = text.trim();
  const m = trimmed.match(/\s*([✓✔⚡]️?)$/u);
  const symbolIcon = m ? (m[1].startsWith('⚡') ? 'bolt' : 'check') : 'none';
  return { text: m ? trimmed.slice(0, m.index).trim() : trimmed, icon: explicit ?? symbolIcon };
};

export const formatZodError = (file: string, err: z.ZodError): string =>
  `${file} has problems:\n` +
  err.issues.map((i) => `  - ${i.path.join('.') || '(root)'}: ${i.message}`).join('\n');
