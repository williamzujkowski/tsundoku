import { vitePreprocess } from '@astrojs/svelte';

// `script: true` is required with @sveltejs/vite-plugin-svelte v7+ (astro 7 /
// @astrojs/svelte 9): vitePreprocess() no longer strips TypeScript from
// <script lang="ts"> by default, so without it raw TS reaches the bundler
// (rolldown) and fails to parse. See #185.
export default {
	preprocess: vitePreprocess({ script: true }),
}
