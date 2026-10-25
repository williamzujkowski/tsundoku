#!/usr/bin/env node
/*
 * Publishes remarque-tokens' prebuilt Palette Deck (deck.css + deck.json)
 * into public/palettes/ so the site serves it as a static asset. The deck
 * is generated and audited in the package itself; we ship its exact bytes.
 * public/palettes/ is gitignored. Runs from `prebuild` and `predev`.
 */
import { copyFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const outDir = join(here, '..', 'public', 'palettes');
mkdirSync(outDir, { recursive: true });
for (const f of ['deck.css', 'deck.json']) copyFileSync(require.resolve(`remarque-tokens/${f}`), join(outDir, f));
console.log(`build-palette-deck: copied remarque-tokens deck.css + deck.json into ${outDir}`);
