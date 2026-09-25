import type { PageLoad } from './$types';

// No redirect guard here: a ripper-only deployment hides /transcoder from
// the nav (see +layout.svelte), but the URL still has to resolve as a deep
// link. +page.svelte renders a full-page empty state and skips fetching
// task data itself when transcoderEnabled is false (see its onMount).
export const load: PageLoad = async () => {
	return {};
};
