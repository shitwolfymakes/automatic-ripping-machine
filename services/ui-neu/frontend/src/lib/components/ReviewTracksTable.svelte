<script lang="ts">
	import type { JobView, TrackView, ScanTitle } from '$lib/types/api.gen';
	import { updateTrack } from '$lib/api/jobs';
	import { reveal } from '$lib/transitions';
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

<div class="border-t border-primary/20 p-4 dark:border-primary/20">
	{#if errorMessage}
		<p in:reveal class="mb-2 text-xs text-red-600 dark:text-red-400">{errorMessage}</p>
	{/if}
	{#if rows.length > 0}
		<div>
			<h4 class="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
				{tracks.length ? 'Tracks' : 'Scanned titles'} ({rows.length})
			</h4>
			<div class="overflow-x-auto rounded-md border border-primary/15 dark:border-primary/20">
				<table class="w-full text-left text-xs">
					<thead class="bg-page text-gray-500 dark:bg-primary/5 dark:text-gray-400">
						<tr>
							<th class="px-3 py-1.5 font-medium">#</th>
							<th class="px-3 py-1.5 font-medium">{isMusic ? 'Name' : 'Title'}</th>
							{#if isVideo}<th class="px-2 py-1.5 font-medium text-center">Episode</th>{/if}
							<th class="px-3 py-1.5 font-medium">Length</th>
							<th class="px-3 py-1.5 font-medium">Source</th>
							{#if isVideo}<th class="w-8"></th>{/if}
						</tr>
					</thead>
					<tbody class="divide-y divide-gray-100 dark:divide-gray-700/50">
						{#each rows as row}
							<tr class="{row.excluded ? 'opacity-40' : ''}">
								<td class="px-3 py-1.5 font-mono text-gray-700 dark:text-gray-300">{row.index}</td>
								<td
									class="px-3 py-1.5 {isVideo && row.trackId ? 'cursor-pointer hover:bg-primary/5 dark:hover:bg-primary/10' : ''}"
									onclick={() => { if (isVideo && row.trackId) toggleTrackSearch(row.trackId!); }}
								>
									{#if row.title}
										<div class="flex items-center gap-1.5">
											<span class="font-medium text-gray-700 dark:text-gray-300">{row.title}</span>
											{#if row.year}
												<span class="text-gray-400">({row.year})</span>
											{/if}
										</div>
									{:else if row.trackId}
										<span class="text-gray-400">{job.title || 'Untitled'}{#if job.year} ({job.year}){/if}</span>
									{:else}
										<span class="text-gray-400">—</span>
									{/if}
								</td>
								{#if isVideo}
									<td class="px-2 py-1.5 text-center">
										{#if row.trackId}
											<input
												type="text"
												value={row.episodeNumber ?? ''}
												onchange={(e) => handleEpisodeNumberInput(row.trackId!, e.currentTarget.value)}
												placeholder="--"
												disabled={row.excluded}
												class="w-10 rounded-sm border border-primary/25 bg-primary/5 px-1 py-0.5 text-center text-xs text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-30 dark:border-primary/30 dark:bg-primary/10 dark:text-white"
											/>
										{:else}
											<span class="text-gray-400">—</span>
										{/if}
									</td>
								{/if}
								<td class="px-3 py-1.5 text-gray-700 dark:text-gray-300">{formatLength(row.durationSeconds)}</td>
								<td class="px-3 py-1.5 font-mono text-gray-500 dark:text-gray-400">{row.sourceLabel}</td>
								{#if isVideo}
									<td class="px-1 py-1.5">
										{#if row.trackId}
											<button
												onclick={() => toggleTrackSearch(row.trackId!)}
												class="rounded p-1 transition-colors {openSearchTrackIds.has(row.trackId) ? 'text-primary' : 'text-gray-400 hover:text-primary dark:text-gray-500 dark:hover:text-primary'}"
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
		<p class="text-sm text-gray-400">No tracks yet.</p>
	{/if}
</div>
