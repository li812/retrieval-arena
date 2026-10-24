import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const here = resolve(__dirname);
const tokens = readFileSync(resolve(here, 'tokens.css'), 'utf8');
// The classic UI's stylesheet moves from app/static to backend/app/static during M1.
const legacyPath = [
  resolve(here, '../../../backend/app/static/style.css'),
  resolve(here, '../../../app/static/style.css'),
].find((p) => existsSync(p));

function block(css: string, selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start === -1) throw new Error(`selector ${selector} not found`);
  const body = css.slice(css.indexOf('{', start) + 1, css.indexOf('}', start));
  const props: Record<string, string> = {};
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    props[m[1]!] = m[2]!.trim().replace(/\s+/g, ' ');
  }
  return props;
}

describe('design tokens', () => {
  it('define the dark and light themes with the three accents', () => {
    const dark = block(tokens, ':root');
    const light = block(tokens, ':root[data-theme="light"]');
    for (const name of [
      '--accent-chroma',
      '--accent-graph',
      '--accent-chat',
      '--bg',
      '--surface',
      '--border',
    ]) {
      expect(dark[name]).toBeTruthy();
      expect(light[name]).toBeTruthy();
    }
  });

  it.skipIf(!legacyPath)('match the classic UI style.css exactly (names and values)', () => {
    const legacy = readFileSync(legacyPath!, 'utf8');
    expect(block(tokens, ':root')).toEqual(block(legacy, ':root'));
    expect(block(tokens, ':root[data-theme="light"]')).toEqual(
      block(legacy, ':root[data-theme="light"]'),
    );
  });
});
