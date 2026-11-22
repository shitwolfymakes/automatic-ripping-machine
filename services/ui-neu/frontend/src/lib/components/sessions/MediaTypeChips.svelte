<script lang="ts">
	// The TYPE filter's chips: All and each media type, each with its
	// count. The pressed chip is the selected type; pressing one selects it.
	import type { MediaType } from '$lib/types/api.gen';

	interface Props {
		/** The count for All and each media type. A type left out shows 0. */
		counts: Partial<Record<MediaType | 'all', number>>;
		/** The selected type, bound to the parent's filter. */
		selected: MediaType | 'all';
		/** One Video chip (keyed `movie`) in place of Movie and TV, for transcode presets, which fit either. */
		videoGroup?: boolean;
	}
	let { counts, selected = $bindable(), videoGroup = false }: Props = $props();

	const MEDIA_TYPES: Array<{ key: MediaType | 'all'; label: string }> = [
		{ key: 'all', label: 'All' },
		{ key: 'movie', label: 'Movie' },
		{ key: 'tv', label: 'TV' },
		{ key: 'music', label: 'Music' },
		{ key: 'data', label: 'Data' },
		{ key: 'iso', label: 'ISO' }
	];
	const VIDEO_GROUP_TYPES: Array<{ key: MediaType | 'all'; label: string }> = [
		{ key: 'all', label: 'All' },
		{ key: 'movie', label: 'Video' },
		...MEDIA_TYPES.filter((c) => c.key !== 'all' && c.key !== 'movie' && c.key !== 'tv')
	];
	const chips = $derived(videoGroup ? VIDEO_GROUP_TYPES : MEDIA_TYPES);
</script>

{#each chips as chip (chip.key)}
	{@const count = counts[chip.key] ?? 0}
	<button
		type="button"
		aria-pressed={selected === chip.key}
		class="chip media-type-chip"
		onclick={() => {
			selected = chip.key;
		}}
	>
		{chip.label}
		{count}
	</button>
{/each}

<style>
	/* chip's default modifiers are all solid-tone; the TYPE filter pills are
	   a plain bordered toggle (border-gray-300 bg-white, selected =
	   border-primary bg-primary), not chip's tinted-background look, so the
	   shape is redrawn here on top of chip's base sizing/cursor/transition. */
	.media-type-chip {
		border: 1px solid var(--color-border-strong);
		border-radius: 9999px;
		background: var(--color-surface-raised);
		padding: 0.125rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.media-type-chip:hover {
		background: var(--color-primary-tint-1);
	}
	.media-type-chip[aria-pressed='true'] {
		border-color: var(--color-primary);
		background: var(--color-primary);
		color: var(--color-on-primary);
	}
</style>
