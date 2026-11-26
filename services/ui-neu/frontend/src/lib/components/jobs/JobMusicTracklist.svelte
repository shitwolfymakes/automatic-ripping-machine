<script lang="ts">
	import type { MusicTrackRow } from '$lib/music/tracks';

	interface Props {
		tracks: MusicTrackRow[];
	}

	let { tracks }: Props = $props();
</script>

<section>
	<h2 class="mb-3 job-detail-section-title">
		Tracklist
		<span class="job-detail-section-subtitle">({tracks.length} tracks via MusicBrainz)</span>
	</h2>
	<div class="overflow-x-auto job-detail-table-scroll">
		<table class="table responsive-table">
			<thead>
				<tr>
					<th class="table-header">#</th>
					<th class="table-header">Title</th>
					<th class="table-header job-detail-right">Duration</th>
				</tr>
			</thead>
			<tbody>
				{#each tracks as mt (mt.number)}
					<tr class="table-row">
						<td class="table-cell" data-label="#">{mt.number}</td>
						<td class="table-cell" data-label="Title">{mt.title}</td>
						<td class="table-cell job-detail-right" data-label="Duration">{mt.durationLabel}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</section>

<style>
	.job-detail-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.job-detail-section-subtitle {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 400;
		color: var(--color-text-muted);
	}
	.job-detail-table-scroll {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}
	.job-detail-right {
		text-align: right;
	}
</style>
