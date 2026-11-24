<script lang="ts">
	import InlineField from '$lib/components/InlineField.svelte';
	import type { MusicTrackRow } from '$lib/utils/music-tracks';

	interface Props {
		tracks: MusicTrackRow[];
		canEdit?: boolean;
		onsave?: (index: number, raw: string) => Promise<void>;
	}

	let { tracks, canEdit = false, onsave }: Props = $props();
</script>

<section>
	<h2 class="mb-3 job-detail-section-title">
		Tracklist
		<span class="job-detail-section-subtitle">({tracks.length} tracks)</span>
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
						<td class="table-cell" data-label="Title">
							<InlineField
								label="Track {mt.number} title"
								value={mt.rawTitle}
								{canEdit}
								onsave={(raw) => onsave?.(mt.number, raw)}
							/>
						</td>
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
