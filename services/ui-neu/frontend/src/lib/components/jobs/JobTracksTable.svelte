<script lang="ts">
	import JobTrackRow from '$lib/components/jobs/JobTrackRow.svelte';
	import type { JobView, NamingPreviewItem, TrackView } from '$lib/types/api.gen';

	interface Props {
		job: JobView;
		tracks: TrackView[];
		tracksAreSeries: boolean;
		previewByTrack: ReadonlyMap<string, NamingPreviewItem>;
		onexcludedchange: (trackId: string, excluded: boolean) => void;
		ontitleapplied: () => void;
	}

	let { job, tracks, tracksAreSeries, previewByTrack, onexcludedchange, ontitleapplied }: Props = $props();

	let editingTrackId = $state<string | null>(null);

	function handleTrackTitleApply() {
		editingTrackId = null;
		ontitleapplied();
	}
</script>

<section>
	<div class="mb-3 flex items-center justify-between">
		<h2 class="job-detail-section-title">
			Tracks ({tracks.length})
		</h2>
	</div>
	<div class="overflow-x-auto job-detail-table-scroll">
		<table class="table responsive-table">
			<thead>
				<tr>
					<th class="table-header">#</th>
					<th class="table-header">Kind</th>
					<th class="table-header">Title</th>
					{#if tracksAreSeries}
						<th class="table-header">Episode</th>
					{/if}
					<th class="table-header">Filename</th>
					<th class="table-header">Length</th>
					<th class="table-header">Size</th>
					<th class="table-header">Include</th>
					<th class="table-header">Rip</th>
					<th class="table-header">Transcode</th>
				</tr>
			</thead>
			<tbody>
				{#each tracks as track (track.id)}
					{@const preview = previewByTrack.get(track.id)}
					<JobTrackRow
						{job}
						{track}
						{preview}
						{tracksAreSeries}
						editing={editingTrackId === track.id}
						ontoggleedit={() => {
							editingTrackId = editingTrackId === track.id ? null : track.id;
						}}
						oncloseedit={() => {
							editingTrackId = null;
						}}
						{onexcludedchange}
						ontitleapplied={handleTrackTitleApply}
					/>
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
	.job-detail-table-scroll {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}
</style>
