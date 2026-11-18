<script lang="ts">
	// The open release in the music search, with its header, tracklist, edit
	// fields, confirmation gates and Apply.
	import type { TrackView, MetadataReleaseDetail, MetadataReleaseTrack } from '$lib/types/api.gen';
	import type { TrackPair } from '$lib/music/release';
	import type { MusicReleaseApply } from '$lib/stores/music-release-apply.svelte';
	import type { MusicReleaseFields } from '$lib/stores/music-release-fields.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import PosterImage from '../../shared/PosterImage.svelte';
	import Glyph from '../../shared/Glyph.svelte';
	import MusicMappingConfirm from './MusicMappingConfirm.svelte';
	import MusicReleaseTracklist from './MusicReleaseTracklist.svelte';

	interface Props {
		/** The open release. */
		detail: MetadataReleaseDetail;
		/** The disc's tracks. */
		discTracks: TrackView[];
		/** The release tracks shown, for the held disc. */
		tracks: MetadataReleaseTrack[];
		/** The title mapping. */
		pairs: TrackPair[];
		/** The shown tracks' total length. */
		mbTotalMs: number;
		/** The disc's total length, null when unknown. */
		discTotalSec: number | null;
		/** The edit fields, which the inputs bind to. */
		fields: MusicReleaseFields;
		/** The gates, the apply state and the feedback line. */
		release: MusicReleaseApply;
		/** Back to results. */
		onback: () => void;
		/** Runs the apply, or opens its next gate. */
		onapply: () => void;
	}
	let { detail, discTracks, tracks, pairs, mbTotalMs, discTotalSec, fields, release, onback, onapply }: Props =
		$props();
</script>

<div class="stack panel-section">
	<button onclick={() => onback()} class="btn music-search-action-btn inline-flex items-center gap-1 self-start"
		><Glyph name="arrow-left" /> Back to results</button
	>
	<div class="flex items-start gap-3">
		<PosterImage url={detail.poster_url} class="h-24 w-24 music-search-detail-poster" />
		<div class="min-w-0 music-search-detail-meta">
			<p class="music-search-detail-title">{detail.title}</p>
			<p>{detail.artist ?? ''}</p>
			<p class="mt-1 flex flex-wrap gap-2">
				{#if detail.country}<span>{detail.country}</span>{/if}
				{#if detail.format}<span>{detail.format}</span>{/if}
				{#if detail.status}<span>{detail.status}</span>{/if}
				{#if detail.disc_count && detail.disc_count > 1}<span>{detail.disc_count} discs</span>{/if}
			</p>
			<p class="mt-0.5 mono music-search-catalog">
				{#if detail.catalog_number}Cat# {detail.catalog_number}{/if}
				{#if detail.barcode}| {detail.barcode}{/if}
			</p>
		</div>
	</div>

	<!-- Tracklist with match indicators -->
	<MusicReleaseTracklist {tracks} {discTracks} {mbTotalMs} {discTotalSec} />

	<!-- Editable fields -->
	<div class="grid grid-cols-2 gap-2">
		<label class="field col-span-2"
			><span class="field-label music-search-field-label-sm">Album</span><input bind:value={fields.album} /></label
		>
		<label class="field"
			><span class="field-label music-search-field-label-sm">Artist</span><input bind:value={fields.artist} /></label
		>
		<label class="field"
			><span class="field-label music-search-field-label-sm">Year</span><input bind:value={fields.year} /></label
		>
		<label class="field"
			><span class="field-label music-search-field-label-sm">Disc #</span><input
				bind:value={fields.discNumber}
				placeholder="-"
			/></label
		>
		<label class="field"
			><span class="field-label music-search-field-label-sm">Disc total</span><input
				bind:value={fields.discTotal}
				placeholder="-"
			/></label
		>
	</div>

	{#if release.confirmMismatch}
		<div class="flex flex-wrap items-center gap-2 alert alert-danger">
			<span class="flex flex-1 items-center gap-1"
				><Glyph name="warning" /> Total length differs, likely the wrong release</span
			>
			<button
				onclick={() => {
					release.acceptMismatch();
					onapply();
				}}
				class="btn music-search-solid-danger music-search-action-btn"
			>
				Apply anyway
			</button>
			<button onclick={() => (release.confirmMismatch = false)} class="btn btn-ghost music-search-action-btn">
				Cancel
			</button>
		</div>
	{/if}

	{#if release.mappingPreview}
		<MusicMappingConfirm
			{pairs}
			onconfirm={() => {
				release.acceptMapping();
				onapply();
			}}
			oncancel={() => (release.mappingPreview = false)}
		/>
	{/if}

	<div class="flex items-center gap-2">
		{#if $isAdmin}
			<button
				onclick={() => onapply()}
				disabled={release.applying || !fields.album.trim()}
				class="btn music-search-success-btn music-search-action-btn"
			>
				{release.applying ? 'Applying...' : 'Apply'}
			</button>
		{/if}
		{#if release.feedback}
			<span class="music-search-feedback" data-tone={release.feedback.type}>{release.feedback.message}</span>
		{/if}
	</div>
</div>

<style>
	/* :global: forwarded through PosterImage's class prop */
	:global(.music-search-detail-poster) {
		border-radius: var(--radius-md);
		object-fit: cover;
	}
	.music-search-detail-meta {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	.music-search-detail-title {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.music-search-catalog {
		font-size: 10px;
	}
	.music-search-field-label-sm {
		font-size: 10px;
	}
	.music-search-solid-danger {
		border: 0;
		background: var(--color-danger);
		color: var(--color-on-primary);
	}
	.music-search-success-btn {
		border: 0;
		background: var(--color-success);
		color: var(--color-on-primary);
	}
	.music-search-success-btn:hover {
		filter: brightness(0.9);
	}
	/* the original action buttons were px-3 py-1.5 (0.75rem/0.375rem),
	   narrower than .btn's default */
	.music-search-action-btn {
		padding: 0.375rem 0.75rem;
		border: 0;
	}
	.music-search-feedback {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.music-search-feedback[data-tone='success'] {
		color: var(--color-success);
	}
	.music-search-feedback[data-tone='error'] {
		color: var(--color-danger);
	}
</style>
