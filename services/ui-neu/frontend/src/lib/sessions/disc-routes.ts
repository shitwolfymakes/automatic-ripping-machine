import type { RecipeCell } from '$lib/components/sessions/RecipeStrip.svelte';
import { resolveSample } from '$lib/sessions/sample-tokens';
import type { DiscRouteSummary } from '$lib/types/api.gen';

const KIND_LABEL: Record<string, string> = { movie: 'Movie', tv: 'TV', music: 'Music CD', data: 'Data', iso: 'ISO' };

/** The display label for a disc kind, or the kind itself when it has none. */
export function discKindLabel(kind: string): string {
	return KIND_LABEL[kind] ?? kind;
}

/** The three RecipeStrip cells (rip, encode, output) for one disc route. */
export function routeCells(route: DiscRouteSummary): RecipeCell[] {
	return [
		{ label: 'Rips', value: route.rip_summary, sub: route.session_name, empty: 'No session' },
		{ label: 'Encodes', value: route.transcode_summary, empty: 'No encode' },
		{
			label: 'Lands in',
			value: route.output_template ? resolveSample(route.output_template, route.kind) : null,
			mono: true,
			empty: 'Not set'
		}
	];
}

/** The sample output path of the first movie route with an output template. */
export function exampleMovie(routes: DiscRouteSummary[]): string | null {
	const movie = routes.find((r) => r.kind === 'movie' && r.output_template);
	return movie?.output_template ? resolveSample(movie.output_template, 'movie') : null;
}
