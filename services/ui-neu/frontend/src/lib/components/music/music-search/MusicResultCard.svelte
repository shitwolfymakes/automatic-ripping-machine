<script lang="ts">
	// One music search result as a flip card, with the release's facts on the
	// front and its tracklist on the back.
	import type { TrackView, MetadataCandidate, MetadataReleaseDetail } from '$lib/types/api.gen';
	import { MATCH_TONE, matchIndicator } from '$lib/jobs/track-match';
	import { formatMinSec } from '$lib/utils/format';
	import PosterImage from '../../shared/PosterImage.svelte';
	import MatchGlyph from './MatchGlyph.svelte';

	interface Props {
		/** The search result this card shows. */
		candidate: MetadataCandidate;
		/** The back face's tracklist, or 'loading'. */
		flipData: MetadataReleaseDetail | 'loading' | undefined;
		/** Whether the card is turned to its back face. */
		flipped: boolean;
		/** The disc's tracks, for the back face's match column. */
		discTracks: TrackView[];
		/** Opens the release. */
		onopen: () => void;
		/** Flips the card over or back. */
		onflip: () => void;
	}
	let { candidate, flipData, flipped, discTracks, onopen, onflip }: Props = $props();

	function flip(e: MouseEvent) {
		e.stopPropagation();
		onflip();
	}
</script>

<div class="music-search-poster-scene">
	<div class="music-search-poster-card" data-flipped={flipped}>
		<!-- FRONT FACE -->
		<div class="music-search-poster-face">
			<button onclick={() => onopen()} class="group flex w-full flex-col music-search-result-card">
				<PosterImage url={candidate.poster_url} class="aspect-square w-full music-search-result-poster" />
				<div class="p-1.5">
					<p class="truncate music-search-result-title">{candidate.title}</p>
					<div class="mt-1 flex flex-wrap items-center gap-1">
						{#if candidate.year}<span class="music-search-result-year">{candidate.year}</span>{/if}
						{#if candidate.release_type}<span class="music-search-result-pill" data-kind="type"
								>{candidate.release_type}</span
							>{/if}
						{#if candidate.format}<span class="music-search-result-pill" data-kind="format">{candidate.format}</span
							>{/if}
						{#if candidate.country}<span class="music-search-result-pill" data-kind="country">{candidate.country}</span
							>{/if}
						{#if candidate.track_count}<span class="music-search-result-pill" data-kind="tracks"
								>{candidate.track_count} tracks</span
							>{/if}
					</div>
				</div>
			</button>
			{#if candidate.track_count}
				<button
					onclick={flip}
					class="absolute top-1 right-1 flex items-center gap-1 music-search-flip-btn"
					title="Flip to see tracklist"
				>
					<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
						/>
					</svg>
					{candidate.track_count} tracks
				</button>
			{/if}
		</div>

		<!-- BACK FACE -->
		<div class="music-search-poster-face music-search-poster-back">
			{#if flipData === 'loading'}
				<div class="flex h-full items-center justify-center music-search-back-loading">
					<svg class="mr-1.5 h-3.5 w-3.5 music-search-spinner" viewBox="0 0 24 24" fill="none">
						<circle class="music-search-spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"
						></circle>
						<path class="music-search-spinner-arc" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
						></path>
					</svg>
					Loading...
				</div>
			{:else if flipData && flipData.tracks && flipData.tracks.length > 0}
				<!-- Compact header -->
				<div class="flex items-center gap-2 music-search-back-header">
					<PosterImage url={flipData.poster_url} class="h-8 w-8 shrink-0 music-search-back-poster" />
					<div class="min-w-0 flex-1">
						<p class="truncate music-search-back-title">{flipData.title}</p>
						<p class="truncate music-search-back-artist">{flipData.artist ?? ''}</p>
					</div>
				</div>
				<!-- Scrollable track list -->
				<div class="min-h-0 flex-1 overflow-y-auto">
					<table class="w-full music-search-back-table">
						<tbody>
							{#each flipData.tracks as track, i (i)}
								{@const kind =
									discTracks.length > 0
										? matchIndicator(track.length_ms, discTracks[i]?.expected_duration_seconds)
										: null}
								<tr class="music-search-back-row">
									<td class="w-6 py-0.5 pl-1.5 pr-1 mono music-search-back-dim music-search-right">{track.position}</td>
									<td class="max-w-0 truncate py-0.5 pr-1 music-search-back-track-title">{track.title}</td>
									<td class="w-10 whitespace-nowrap py-0.5 pr-1 mono music-search-back-dim music-search-right"
										>{formatMinSec(track.length_ms, 1000)}</td
									>
									{#if kind}<td class="w-4 py-0.5 pr-1 music-search-match" data-tone={MATCH_TONE[kind]} title={kind}
											><MatchGlyph {kind} /></td
										>{/if}
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{:else}
				<div class="flex h-full items-center justify-center music-search-back-empty">No track data</div>
			{/if}
			<!-- Flip-back button -->
			<button
				onclick={flip}
				class="absolute top-1 right-1 flex items-center gap-1 music-search-flip-btn"
				title="Flip back"
			>
				<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
					/>
				</svg>
				Back
			</button>
		</div>
	</div>
</div>

<style>
	.music-search-right {
		text-align: right;
	}
	.music-search-spinner {
		animation: music-search-spin 1s linear infinite;
	}
	.music-search-spinner-track {
		opacity: 0.25;
	}
	.music-search-spinner-arc {
		opacity: 0.75;
	}
	@keyframes music-search-spin {
		to {
			transform: rotate(360deg);
		}
	}

	.music-search-poster-scene {
		perspective: 800px;
	}
	.music-search-poster-card {
		position: relative;
		transform-style: preserve-3d;
		transition: transform 0.5s;
	}
	.music-search-poster-card[data-flipped='true'] {
		transform: rotateY(180deg);
	}
	.music-search-poster-face {
		position: relative;
		backface-visibility: hidden;
	}
	.music-search-poster-back {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface-raised);
		transform: rotateY(180deg);
	}
	.music-search-result-card {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		text-align: left;
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.music-search-result-poster) {
		border-top-left-radius: var(--radius-md);
		border-top-right-radius: var(--radius-md);
	}
	.music-search-result-title {
		font-size: 11px;
		font-weight: 500;
		color: var(--color-text);
	}
	.music-search-result-year {
		font-size: 10px;
		color: var(--color-text-muted);
	}
	.music-search-result-pill {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.25rem;
		font-size: 10px;
		font-weight: 500;
	}
	.music-search-result-pill[data-kind='type'] {
		background: color-mix(in srgb, var(--color-accent-3) 15%, transparent);
		color: var(--color-accent-3);
	}
	.music-search-result-pill[data-kind='format'] {
		background: var(--color-success-soft);
		color: var(--color-on-success-soft);
	}
	.music-search-result-pill[data-kind='country'] {
		background: var(--color-primary-tint-2);
		color: var(--color-text-secondary);
	}
	.music-search-result-pill[data-kind='tracks'] {
		background: var(--color-info-soft);
		color: var(--color-on-info-soft);
	}
	.music-search-flip-btn {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		font-size: 10px;
		font-weight: 500;
		color: var(--color-on-primary);
		background: color-mix(in srgb, var(--color-on-frame-accent) 60%, transparent);
		backdrop-filter: blur(4px);
		transition: background-color var(--motion-fast) var(--ease);
	}
	.music-search-flip-btn:hover {
		background: color-mix(in srgb, var(--color-on-frame-accent) 80%, transparent);
	}
	.music-search-back-loading {
		font-size: 11px;
		color: var(--color-text-muted);
	}
	.music-search-back-header {
		border-bottom: 1px solid var(--color-border);
		padding: 0.375rem;
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.music-search-back-poster) {
		border-radius: var(--radius-sm);
	}
	.music-search-back-title {
		font-size: 11px;
		font-weight: 600;
		color: var(--color-text);
	}
	.music-search-back-artist {
		font-size: 10px;
		color: var(--color-text-muted);
	}
	.music-search-back-table {
		font-size: 11px;
	}
	.music-search-back-row {
		border-bottom: 1px solid var(--color-border);
	}
	.music-search-back-row:last-child {
		border-bottom: 0;
	}
	.music-search-back-dim {
		color: var(--color-text-faint);
	}
	.music-search-back-track-title {
		color: var(--color-text-secondary);
	}
	.music-search-back-empty {
		font-size: 10px;
		color: var(--color-text-faint);
	}

	.music-search-match {
		text-align: center;
	}
	.music-search-match[data-tone='success'] {
		color: var(--color-success);
	}
	.music-search-match[data-tone='warning'] {
		color: var(--color-on-warning-soft);
	}
	.music-search-match[data-tone='danger'] {
		color: var(--color-danger);
	}
	.music-search-match[data-tone='muted'] {
		color: var(--color-text-faint);
	}
</style>
