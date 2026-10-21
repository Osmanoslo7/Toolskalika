import { loadFont } from '@remotion/fonts';
import { staticFile } from 'remotion';
import { theme } from './theme';

let fontsReady: Promise<void> | null = null;

export const loadBrandFonts = (): Promise<void> => {
  if (!fontsReady) {
    fontsReady = Promise.all(
      theme.fontFiles.map((f) =>
        loadFont({ family: f.family, weight: f.weight, url: staticFile(f.file), display: 'block' }),
      ),
    ).then(() => undefined);
  }
  return fontsReady;
};
