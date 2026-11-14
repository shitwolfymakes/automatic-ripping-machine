<script lang="ts">
	// The chosen release's tracklist, with each track's disc length and match
	// when the disc's tracks are known, and the totals.
	import type { TrackView, MetadataReleaseTrack } from '$lib/types/api.gen';
	import { MATCH_TONE, matchIndicator } from '$lib/jobs/track-match';
	import { formatMinSec } from '$lib/utils/format';
	import MatchGlyph from './MatchGlyph.svelte';

	interface Props {
		/** The release tracks shown, for the held disc. */
		tracks: MetadataReleaseTrack[];
		/** The disc's tracks, for the disc length and match columns. */
		discTracks: TrackView[];
		/** The shown tracks' total length. */
		mbTotalMs: number;
		/** The disc's total length, null when unknown. */
		discTotalSec: number | null;
	}
	let { tracks, discTracks, mbTotalMs, discTotalSec }: Props = $props();
</script>

<div class="overflow-x-auto music-search-table-scroll">
	<table class="table music-search-detail-table">
		<thead>
			<tr
				><th class="table-header">#</th><th class="table-header">Title</th>{#if discTracks.length > 0}<th
						class="table-header music-search-right">Disc Length</th
					>{/if}<th class="table-header music-search-right">{discTracks.length > 0 ? 'Match Length' : 'Duration'}</th
				>{#if discTracks.length > 0}<th class="table-header music-search-center">Match</th>{/if}</tr
			>
		</thead>
		<tbody>
			{#each tracks as t, i (i)}
				{@const kind = matchIndicator(t.length_ms, discTracks[i]?.expected_duration_seconds)}
				<tr class="table-row">
					<td class="table-cell">{t.position ?? i + 1}</td>
					<td class="table-cell">{t.title}</td>
					{#if discTracks.length > 0}<td class="table-cell mono music-search-right music-search-muted"
							>{formatMinSec(discTracks[i]?.expected_duration_seconds, 1)}</td
						>{/if}
					<td class="table-cell music-search-right">{formatMinSec(t.length_ms, 1000)}</td>
					{#if discTracks.length > 0}<td class="table-cell music-search-match" data-tone={MATCH_TONE[kind]} title={kind}
							><MatchGlyph {kind} /></td
						>{/if}
				</tr>
			{/each}
		</tbody>
		{#if discTracks.length > 0}
			{@const totalKind = matchIndicator(mbTotalMs, discTotalSec)}
			<tfoot class="music-search-tfoot">
				<tr>
					<td class="table-cell">Total</td>
					<td class="table-cell"></td>
					<td class="table-cell mono music-search-right">{formatMinSec(discTotalSec, 1)}</td>
					<td class="table-cell mono music-search-right">{formatMinSec(mbTotalMs, 1000)}</td>
					<td class="table-cell music-search-match" data-tone={MATCH_TONE[totalKind]} title={totalKind}
						><MatchGlyph kind={totalKind} /></td
					>
				</tr>
			</tfoot>
		{/if}
	</table>
</div>

<style>
	.music-search-right {
		text-align: right;
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
	.music-search-table-scroll {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
	}
	.music-search-detail-table {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.music-search-detail-table .table-header,
	.music-search-detail-table .table-cell {
		padding: 0.25rem 0.5rem;
	}
	.music-search-center {
		text-align: center;
	}
	.music-search-muted {
		color: var(--color-text-muted);
	}
	.music-search-tfoot {
		border-top: 1px solid var(--color-border);
		background: var(--color-surface-raised);
		font-weight: 500;
	}
</style>
