<script lang="ts">
	import type { JobView, TrackView, ScanTitle } from '$lib/types/api.gen';
	import { updateTrack } from '$lib/api/jobs';
	import { trackToRow, scanTitleToRow } from '$lib/utils/review-rows';
	import TrackTitleSearch from './TrackTitleSearch.svelte';

	interface Props {
		job: JobView;
		tracks: TrackView[];
		scanTitles?: ScanTitle[];
		isVideo: boolean;
		isMusic: boolean;
		onrefresh?: () => void;
	}
	let { job, tracks, scanTitles = [], isVideo, isMusic, onrefresh }: Props = $props();

	// Materialized tracks always win; scanned titles are the pre-rip fallback.
	let rows = $derived(tracks.length ? tracks.map(trackToRow) : scanTitles.map(scanTitleToRow));

	let openSearchTrackIds = $state<Set<string>>(new Set());
	let savingTrackField = $state<string | null>(null);
	let errorMessage = $state<string | null>(null);

	async function handleTrackFieldUpdate(
		trackId: string,
		field: 'episode_number' | 'episode_name' | 'excluded',
		value: number | string | boolean | null
	) {
		savingTrackField = `${trackId}-${field}`;
		errorMessage = null;
		try {
			await updateTrack(job.id, trackId, { [field]: value });
			onrefresh?.();
		} catch (e) {
			errorMessage = `Failed to update track: ${e instanceof Error ? e.message : 'Unknown error'}`;
		} finally {
			savingTrackField = null;
		}
	}

	function handleEpisodeNumberInput(trackId: string, raw: string) {
		const trimmed = raw.trim();
		const n = trimmed === '' ? null : Number(trimmed);
		handleTrackFieldUpdate(trackId, 'episode_number', Number.isFinite(n) ? n : null);
	}

	function toggleTrackSearch(trackId: string) {
		const next = new Set(openSearchTrackIds);
		if (next.has(trackId)) next.delete(trackId);
		else next.add(trackId);
		openSearchTrackIds = next;
	}

	function handleTrackTitleApply(trackId?: string) {
		if (trackId != null) {
			openSearchTrackIds = new Set([...openSearchTrackIds].filter((id) => id !== trackId));
		} else {
			openSearchTrackIds = new Set();
		}
		onrefresh?.();
	}

	function formatLength(secs: number | null | undefined): string {
		if (!secs) return '--';
		const h = Math.floor(secs / 3600);
		const m = Math.floor((secs % 3600) / 60);
		const s = secs % 60;
		if (h > 0) return `${h}h ${m}m ${s}s`;
		return `${m}m ${s}s`;
	}
</script>

<div class="review-tracks-table-wrap">
	{#if errorMessage}
		<p class="field-error mb-2">{errorMessage}</p>
	{/if}
	{#if rows.length > 0}
		<div>
			<h4 class="mb-2 review-tracks-table-heading">
				{tracks.length ? 'Tracks' : 'Scanned titles'} ({rows.length})
			</h4>
			<div class="overflow-x-auto review-tracks-table-scroll">
				<table class="table review-tracks-table">
					<thead>
						<tr>
							<th class="table-header">#</th>
							<th class="table-header">{isMusic ? 'Name' : 'Title'}</th>
							{#if isVideo}<th class="table-header review-tracks-table-center">Episode</th>{/if}
							<th class="table-header">Length</th>
							<th class="table-header">Source</th>
							{#if isVideo}<th class="table-header w-8"></th>{/if}
						</tr>
					</thead>
					<tbody>
						{#each rows as row}
							<tr class="table-row" data-disabled={row.excluded}>
								<td class="table-cell mono">{row.index}</td>
								<td
									class="table-cell {isVideo && row.trackId ? 'review-tracks-table-clickable' : ''}"
									onclick={() => { if (isVideo && row.trackId) toggleTrackSearch(row.trackId!); }}
								>
									{#if row.title}
										<div class="flex items-center gap-1.5">
											<span class="review-tracks-table-title">{row.title}</span>
											{#if row.year}
												<span class="review-tracks-table-faint">({row.year})</span>
											{/if}
										</div>
									{:else if row.trackId}
										<span class="review-tracks-table-faint">{job.title || 'Untitled'}{#if job.year} ({job.year}){/if}</span>
									{:else}
										<span class="review-tracks-table-faint">-</span>
									{/if}
								</td>
								{#if isVideo}
									<td class="table-cell review-tracks-table-center">
										{#if row.trackId}
											<input
												type="text"
												value={row.episodeNumber ?? ''}
												onchange={(e) => handleEpisodeNumberInput(row.trackId!, e.currentTarget.value)}
												placeholder="--"
												disabled={row.excluded}
												class="field-control review-tracks-table-episode-input"
											/>
										{:else}
											<span class="review-tracks-table-faint">-</span>
										{/if}
									</td>
								{/if}
								<td class="table-cell review-tracks-table-secondary">{formatLength(row.durationSeconds)}</td>
								<td class="table-cell mono review-tracks-table-muted">{row.sourceLabel}</td>
								{#if isVideo}
									<td class="table-cell">
										{#if row.trackId}
											<button
												onclick={() => toggleTrackSearch(row.trackId!)}
												class="btn btn-icon review-tracks-table-search-btn"
												aria-pressed={openSearchTrackIds.has(row.trackId)}
												title={openSearchTrackIds.has(row.trackId) ? 'Close search' : 'Search title'}
											>
												<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
													<circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
												</svg>
											</button>
										{/if}
									</td>
								{/if}
							</tr>
							{#if isVideo && row.trackId && openSearchTrackIds.has(row.trackId)}
								<tr>
									<td colspan="99" class="px-3 py-2">
										<TrackTitleSearch jobId={job.id} track={tracks.find((t) => t.id === row.trackId)!} onapply={() => handleTrackTitleApply(row.trackId!)} onclear={() => onrefresh?.()} onclose={() => toggleTrackSearch(row.trackId!)} />
									</td>
								</tr>
							{/if}
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	{:else}
		<p class="review-tracks-table-empty">No tracks yet.</p>
	{/if}
</div>

<style>
	.review-tracks-table-wrap { border-top: 1px solid var(--color-border); padding: 1rem; }
	.review-tracks-table-scroll { border: 1px solid var(--color-border); border-radius: var(--radius-md); }
	/* the original was px-3 py-1.5 (px-2 for the Episode column), between
	   table's own default padding and table-compact's - a custom override
	   rather than either preset */
	.review-tracks-table { font-size: 0.75rem; line-height: 1rem; }
	.review-tracks-table .table-header, .review-tracks-table .table-cell { padding: 0.375rem 0.75rem; }
	.review-tracks-table-center { text-align: center; padding-left: 0.5rem; padding-right: 0.5rem; }
	.table-row[data-disabled="true"] { opacity: 0.4; }
	.review-tracks-table-clickable { cursor: pointer; }
	.review-tracks-table-clickable:hover { background: var(--color-primary-tint-1); }
	.review-tracks-table-episode-input { width: 2.5rem; min-height: auto; padding: 0.125rem 0.25rem; text-align: center; }
	.review-tracks-table-search-btn[aria-pressed="true"] { color: var(--color-primary); }
	.review-tracks-table-heading { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-text-secondary); }
	.review-tracks-table-title { font-weight: 500; color: var(--color-text-secondary); }
	.review-tracks-table-faint { color: var(--color-text-faint); }
	.review-tracks-table-secondary { color: var(--color-text-secondary); }
	.review-tracks-table-muted { color: var(--color-text-muted); }
	.review-tracks-table-empty { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-faint); }
</style>
