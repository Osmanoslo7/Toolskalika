import React, { useEffect, useState } from 'react';
import { continueRender, delayRender } from 'remotion';
import { loadBrandFonts } from '../fonts';

// Children (which measure text) only mount once brand fonts are loaded,
// and the frame is not captured until they have.
export const FontGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [handle] = useState(() => delayRender('Waiting for brand fonts'));
  const [ready, setReady] = useState(false);

  useEffect(() => {
    loadBrandFonts().then(() => setReady(true));
  }, []);

  useEffect(() => {
    if (ready) continueRender(handle);
  }, [ready, handle]);

  return ready ? <>{children}</> : null;
};
