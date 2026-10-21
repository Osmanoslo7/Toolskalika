// Brand theme for Ironhand Studio. Edit this file to restyle every template.
// Colors were sampled from the Ironhand poster; fonts are open-licensed lookalikes.

export const theme = {
  colors: {
    goldSheen: '#FDF3A0',
    gold: '#FBC146',
    goldDeep: '#E68F1E',
    bg: '#090807',
    panel: '#23211C',
    silver: '#F8F6F4',
    silverMid: '#C7C7C6',
    ink: '#000000',
  },
  gradients: {
    gold: 'linear-gradient(180deg, #FDF3A0 0%, #FBC146 45%, #E68F1E 100%)',
    silver: 'linear-gradient(180deg, #FFFFFF 0%, #F8F6F4 45%, #A9A7A4 100%)',
    goldEdge: 'linear-gradient(145deg, #FDF3A0, #E68F1E 35%, #3a2a10 55%, #FBC146 80%, #E68F1E)',
  },
  fonts: {
    display: 'Anton',
    heavy: 'Montserrat',
    tracked: 'Rajdhani',
  },
  // Font files live in public/fonts (see src/fonts.ts).
  fontFiles: [
    { family: 'Anton', weight: '400', file: 'fonts/anton-latin-400-normal.woff2' },
    { family: 'Montserrat', weight: '600', file: 'fonts/montserrat-latin-600-normal.woff2' },
    { family: 'Montserrat', weight: '800', file: 'fonts/montserrat-latin-800-normal.woff2' },
    { family: 'Montserrat', weight: '900', file: 'fonts/montserrat-latin-900-normal.woff2' },
    { family: 'Rajdhani', weight: '600', file: 'fonts/rajdhani-latin-600-normal.woff2' },
    { family: 'Rajdhani', weight: '700', file: 'fonts/rajdhani-latin-700-normal.woff2' },
  ],
  video: {
    width: 1080,
    height: 1920,
    fps: 30,
  },
  // Areas covered by TikTok / Reels / Shorts UI on a 1080x1920 frame.
  safe: {
    top: 150,
    bottom: 1620,
    rightRailX: 960,
    rightRailTop: 880,
    side: 48,
  },
  timing: {
    logoStingFrames: 21, // 0.7s, overlaid on the hook, never before it
    endCardSeconds: 2.5,
    endCardFadeFrames: 6,
  },
  captions: {
    fontSize: 78,
    maxCharsPerPage: 22,
    maxWordsPerPage: 3,
    maxGapSeconds: 0.45,
  },
  brandName: 'IRONHAND',
  brandSub: 'STUDIO',
} as const;

export type Theme = typeof theme;
