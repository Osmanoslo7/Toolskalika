# Ironhand Promo Studio

Turns your real footage into branded vertical promo videos (1080×1920, 30 fps, H.264,
loudness-normalized) for Ironhand Studio. Everything runs on your machine: Remotion
renders the video, FFmpeg prepares footage and audio, faster-whisper writes the captions.

Templates: **Before/After** (ready). 3 Mistakes and Build Time-lapse are next.

## License note (Remotion)

Remotion is free, including for commercial videos, for individuals and for companies with
**up to 3 employees**. Above that you need a Company License (remotion.pro). You may not sell
or relicense your own modified version of Remotion itself. The bundled license says terms
change slightly in Remotion 5.0, so re-read it before upgrading. Fonts are SIL OFL (licenses
in `public/fonts`); faster-whisper and the Whisper models are MIT.

## One-time setup

You need **Node 20+**, **FFmpeg** (with ffprobe), and **Python 3.10+** (for captions).

```bash
cd promo-studio
npm install
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip install -r requirements.txt
```

- First render: Remotion downloads its own headless Chrome (one time, free).
- First transcription: faster-whisper downloads the `small.en` model (~480 MB, one time,
  free) into `~/.cache/huggingface`. After that both work offline.

Check the install with the bundled sample (placeholder footage):

```bash
npm run render -- sample-before-after
# -> projects/sample-before-after/out/sample-before-after.mp4
```

## Make a video

**1. Create the project**

```bash
npm run new -- bakery-redesign
```

**2. Drop your clips into `projects/bakery-redesign/raw/`**

| File | What | Tips |
|---|---|---|
| `talking-head.mp4` | You, vertical, phone | Say the hook first. Dead air at the start/end is trimmed automatically. iPhone HDR is tone-mapped for you. |
| `old-site.mp4` | Screen recording of the old site | Record the **mobile view**: your phone's screen recorder, or Chrome DevTools device mode (iPhone size). Desktop recordings get cropped. |
| `new-site.mp4` | Screen recording of your redesign | Same. Start at the top, scroll slowly. Keep the WhatsApp button in view. |

Any file names/formats work (`.mov`, HEVC, variable frame rate); set them in `project.json`.

**3. Edit `project.json` and `notes.md`** (see the reference below). Put your script or
bullet points in `notes.md`; brand names in it help Whisper spell them right.

**4. Build it**

```bash
npm run make -- bakery-redesign
```

This runs prep → transcribe → render and writes
`projects/bakery-redesign/out/bakery-redesign.mp4`, then prints its codec, frame rate and
loudness so you can confirm it's upload-ready.

**5. Fix captions, tweak, re-render**

- Open `projects/bakery-redesign/captions.json`, fix any word, delete fillers ("um"),
  add `"emphasis": true` to keep a word gold, or `"break": true` to start a new caption.
- Preview live with your footage: `npm run preview -- bakery-redesign` (Remotion Studio,
  scrub the timeline, toggle `showSafeZones`).
- Re-render: `npm run render -- bakery-redesign` (only re-renders; prep and captions are reused).

### Your edits always win

- `captions.json` is created once and **never overwritten**. Whisper's raw output goes to
  `captions.auto.json`.
- `corrections` in `project.json` (e.g. `"iron hand": "Ironhand"`) are applied only to words
  you haven't touched.
- If you re-record the talking head, `transcribe` warns that `captions.json` is stale.
  `npm run transcribe -- <name> --reset` starts captions fresh.

## project.json reference (Before/After)

Comments below are explanation only; the real file is plain JSON (no `//`).

```jsonc
{
  "template": "before-after",
  "hook": "Your website is losing customers",          // top headline, on screen from frame 0
  "talkingHead": { "file": "raw/talking-head.mp4",
                   "trimStart": "auto", "trimEnd": "auto",   // or seconds
                   "focusY": 0.38 },                         // where your face sits (0 top, 1 bottom)
  "before": { "file": "raw/old-site.mp4", "label": "BEFORE" },  // optional trimStart/trimEnd
  "after":  { "file": "raw/new-site.mp4", "label": "AFTER" },
  "wipe": { "at": "@after", "sweep": 1.6, "peekHold": 1 },     // half-way pause = side-by-side
  "callouts": [
    { "text": "Mobile ✓", "at": "@phones" },                   // ✓ → check icon
    { "text": "WhatsApp button ✓", "at": "@whatsapp" },
    { "text": "Fast ⚡", "at": "@fast", "until": "@want" }     // ⚡ → bolt icon; until = disappear
  ],
  "endCard": { "title": "Free website audit", "subtitle": "link in bio", "seconds": 2.5 },
  "captions": { "language": "en", "model": "small.en",
                "vocabulary": ["Ironhand", "WhatsApp"],
                "corrections": { "iron hand": "Ironhand", "whats app": "WhatsApp" } },
  "mascot": { "full": "brand/mascot.png", "head": "brand/mascot-head.png" },
  "showSafeZones": false
}
```

**Times** can be seconds (`7.5`) or anchored to what you say, so they follow your delivery
when you re-record:
`"@after"` (first time you say "after"), `"@after#2"` (second time), `"@after+0.3"` / `"@after-0.2"`.

Up to 3 callouts fit on screen at once. Better accuracy for accents: set `"model": "medium.en"`
(slower).

## Brand

Colors, fonts, timings and safe zones are all in **`src/theme.ts`**.

The mascot images in `public/brand/` are **placeholder crops from your poster**. Replace
them, keeping the names:

- `mascot.png`: the character alone on a **transparent background**, ≥2000 px tall
  (end card, pointing at the CTA)
- `mascot-head.png`: square crop of the head (logo sting badge)

## Rules built into the template

- The hook (headline, footage, your voice) is on screen at frame 0. The logo sting is a
  0.7 s corner flash over the hook, never a card in front of it.
- Captions and callouts stay out of the areas TikTok/Reels cover (bottom ~300 px, right rail).
  Turn on `showSafeZones` to see them.
- Animations enter, point, and get out of the way; nothing covers your face or the site.

## Troubleshooting

- **No Chrome download possible / offline:** set `REMOTION_BROWSER_EXECUTABLE` to an existing
  Chrome or Chromium binary.
- **"Your first word starts at 1.6s"**: trim the start (`trimStart`) or re-record; the hook
  must land in the first second.
- **Captions out of sync after changing trims:** run `npm run transcribe -- <name> --reset`.
- **Tests:** `npm test` (caption paging, merge rules, anchors, loudness parsing, transcription shaping).

## Layout

```
src/theme.ts                  brand: colors, fonts, timings, safe zones
src/shared/                   captions, logo sting, end card, phone mockup, wipe, callouts…
src/templates/before-after/   the Before/After composition + its props schema
scripts/cli.ts                new / prep / transcribe / props / preview / render / make
scripts/transcribe.py         faster-whisper, word timestamps
projects/<name>/              project.json, notes.md, raw/, captions.json, out/
```
