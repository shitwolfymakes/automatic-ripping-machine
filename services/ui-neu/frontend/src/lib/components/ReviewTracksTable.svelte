<script lang="ts">
	import type { JobView, TrackView } from '$lib/types/api.gen';
	import { updateTrack } from '$lib/api/jobs';
	import TrackTitleSearch from './TrackTitleSearch.svelte';

	interface Props {
		job: JobView;
		tracks: TrackView[];
		isVideo: boolean;
		isMusic: boolean;
		onrefresh?: () => void;
	}
	let { job, tracks, isVideo, isMusic, onrefresh }: Props = $props();

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
		<p class="mb-2 text-xs text-red-600 dark:text-red-400">{errorMessage}</p>
	{/if}
	{#if tracks.length > 0}
		<div>
			<h4 class="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">Tracks ({tracks.length})</h4>
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
						{#each tracks as track}
							<tr class="{track.excluded ? 'opacity-40' : ''}">
								<td class="px-3 py-1.5 font-mono text-gray-700 dark:text-gray-300">{track.index}</td>
								<td
									class="px-3 py-1.5 {isVideo ? 'cursor-pointer hover:bg-primary/5 dark:hover:bg-primary/10' : ''}"
									onclick={() => { if (isVideo) toggleTrackSearch(track.id); }}
								>
									{#if track.title}
										<div class="flex items-center gap-1.5">
											<span class="font-medium text-gray-700 dark:text-gray-300">{track.title}</span>
											{#if track.year}
												<span class="text-gray-400">({track.year})</span>
											{/if}
										</div>
									{:else}
										<span class="text-gray-400">{job.title || 'Untitled'}{#if job.year} ({job.year}){/if}</span>
									{/if}
								</td>
								{#if isVideo}
									<td class="px-2 py-1.5 text-center">
										<input
											type="text"
											value={track.episode_number ?? ''}
											onchange={(e) => handleEpisodeNumberInput(track.id, e.currentTarget.value)}
											placeholder="--"
											disabled={track.excluded}
											class="w-10 rounded-sm border border-primary/25 bg-primary/5 px-1 py-0.5 text-center text-xs text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-30 dark:border-primary/30 dark:bg-primary/10 dark:text-white"
										/>
									</td>
								{/if}
								<td class="px-3 py-1.5 text-gray-700 dark:text-gray-300">{formatLength(track.duration_seconds)}</td>
								<td class="px-3 py-1.5 font-mono text-gray-500 dark:text-gray-400">{track.output_path || track.source_ref}</td>
								{#if isVideo}
									<td class="px-1 py-1.5">
										<button
											onclick={() => toggleTrackSearch(track.id)}
											class="rounded p-1 transition-colors {openSearchTrackIds.has(track.id) ? 'text-primary' : 'text-gray-400 hover:text-primary dark:text-gray-500 dark:hover:text-primary'}"
											title={openSearchTrackIds.has(track.id) ? 'Close search' : 'Search title'}
										>
											<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
												<circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
											</svg>
										</button>
									</td>
								{/if}
							</tr>
							{#if isVideo && openSearchTrackIds.has(track.id)}
								<tr>
									<td colspan="99" class="px-3 py-2">
										<TrackTitleSearch jobId={job.id} {track} onapply={() => handleTrackTitleApply(track.id)} onclear={() => onrefresh?.()} onclose={() => toggleTrackSearch(track.id)} />
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
