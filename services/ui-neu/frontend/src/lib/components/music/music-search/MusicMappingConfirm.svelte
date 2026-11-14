<script lang="ts">
	// The title mapping preview shown before a release's track titles are
	// written onto the disc's tracks, with Apply titles and Cancel.
	import type { TrackPair } from '$lib/music/release';
	import { MATCH_TONE } from '$lib/jobs/track-match';
	import { formatMinSec } from '$lib/utils/format';
	import Glyph from '../../shared/Glyph.svelte';
	import MatchGlyph from './MatchGlyph.svelte';

	interface Props {
		/** The disc track and release track pairs shown. */
		pairs: TrackPair[];
		/** Apply titles. */
		onconfirm: () => void;
		/** Cancel. */
		oncancel: () => void;
	}
	let { pairs, onconfirm, oncancel }: Props = $props();
</script>

<div class="stack panel-section music-search-mapping-preview">
	<p class="music-search-mapping-title">Confirm track title mapping</p>
	<div class="overflow-x-auto music-search-table-scroll">
		<table class="table">
			<tbody>
				{#each pairs as p, i (i)}
					<tr class="table-row">
						<td class="table-cell whitespace-nowrap mono music-search-muted"
							>Disc #{p.disc.index} ({formatMinSec(p.disc.expected_duration_seconds, 1)})</td
						>
						<td class="table-cell music-search-center music-search-faint"
							><Glyph name="arrow-right" class="mx-auto h-3.5 w-3.5" /></td
						>
						<td class="table-cell">{p.mb.title}</td>
						<td class="table-cell music-search-right mono music-search-muted">{formatMinSec(p.mb.length_ms, 1000)}</td>
						<td class="table-cell music-search-match" data-tone={MATCH_TONE[p.match]} title={p.match}
							><MatchGlyph kind={p.match} /></td
						>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<div class="flex items-center gap-2">
		<button onclick={() => onconfirm()} class="btn music-search-success-btn music-search-action-btn">
			Apply titles
		</button>
		<button onclick={() => oncancel()} class="btn btn-ghost music-search-action-btn"> Cancel </button>
	</div>
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
	.music-search-center {
		text-align: center;
	}
	.music-search-muted {
		color: var(--color-text-muted);
	}
	.music-search-faint {
		color: var(--color-text-faint);
	}
	.music-search-mapping-preview {
		border-color: color-mix(in srgb, var(--color-primary) 30%, transparent);
	}
	.music-search-mapping-title {
		font-weight: 500;
		color: var(--color-text-secondary);
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
</style>
