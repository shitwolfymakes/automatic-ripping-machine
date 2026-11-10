<script lang="ts">
	// A session's or preset's media type as a pill, coloured by type.
	// Five media-type hues (movie/tv/music/data/iso) with no dedicated block:
	// mapped onto existing tone/accent tokens rather than inventing new ones
	// (same soft-bg + accent-fg pairing PosterImage.svelte uses for its
	// fallback tile). data-media on the tag selects the pairing below.
	import type { MediaType } from '$lib/types/api.gen';
	import { humanizeMediaType } from '$lib/utils/preset-labels';

	interface Props {
		mediaType: MediaType;
	}
	let { mediaType }: Props = $props();
</script>

<span class="badge badge-sm media-pill" data-media={mediaType}>
	{humanizeMediaType(mediaType)}
</span>

<style>
	/* original: rounded px-2 py-0.5 text-xs font-semibold uppercase
	   tracking-wide - badge-sm's own size (0.625rem)/tracking (0.06em)/
	   padding (0 0.375rem) are tuned for the BUILT-IN/RECOMMENDED tag look,
	   visibly smaller than this media pill's text-xs (0.75rem)/tracking-wide
	   (0.025em)/px-2 py-0.5, so both are restated here. */
	.media-pill {
		flex-shrink: 0;
		padding: 0.125rem 0.5rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 600;
		letter-spacing: 0.025em;
	}
	/* soft-bg + accent/tone-fg pairing per media type, mirroring
	   PosterImage.svelte's --color-info-soft/--color-accent-2 fallback tile:
	   movie(blue)->info, tv(violet)->accent-3, music(green)->success,
	   iso(amber)->warning, data(gray)->neutral tint/secondary text. */
	.media-pill[data-media='movie'] {
		background: var(--color-info-soft);
		color: var(--color-on-info-soft);
	}
	.media-pill[data-media='tv'] {
		background: color-mix(in srgb, var(--color-accent-3) 15%, transparent);
		color: var(--color-accent-3);
	}
	.media-pill[data-media='music'] {
		background: var(--color-success-soft);
		color: var(--color-on-success-soft);
	}
	/* original gray-100 (rgb 243,244,246) is within a few RGB units of this
	   card's own surface background (rgb 241,247,255) - visually no pill box
	   at all, just bold text; transparent reproduces that exactly instead of
	   introducing a visible box no available neutral token avoids. */
	.media-pill[data-media='data'] {
		background: transparent;
		color: var(--color-text-secondary);
	}
	/* dark WAS visible (gray-700 at 30% alpha), unlike light - the strict
	   token set forbids a literal wash even where no dedicated neutral-grey
	   role exists, so this collapses onto --color-backdrop (a fixed-black
	   token, unlike --color-text which is near-white in dark mode and would
	   lighten rather than darken the surface) scaled down via color-mix
	   (recorded as a deviation if it pushes a screen over threshold). */
	/* token collapse: scaled backdrop stands in for the literal grey wash */
	:global(.dark) .media-pill[data-media='data'] {
		background: color-mix(in srgb, var(--color-backdrop) 30%, transparent);
	}
	.media-pill[data-media='iso'] {
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
</style>
