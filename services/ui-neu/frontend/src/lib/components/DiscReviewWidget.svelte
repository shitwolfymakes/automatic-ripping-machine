<script lang="ts">
	import { onMount } from 'svelte';
	import type { JobView, JobDetailView, TrackView } from '$lib/types/api.gen';
	import { abandonJob, fetchJob, updateTrack, patchJob, startWaitingJob } from '$lib/api/jobs';
	import CountdownTimer from './CountdownTimer.svelte';
	import { discTypeLabel } from '$lib/utils/job-type';
	import PosterImage from './PosterImage.svelte';
	import TitleSearch from './TitleSearch.svelte';
	import MusicSearch from './MusicSearch.svelte';
	import ApplySessionDialog from './ApplySessionDialog.svelte';
	import DiscTypeIcon from './DiscTypeIcon.svelte';
	import TrackTitleSearch from './TrackTitleSearch.svelte';
	import SkeletonCard from './SkeletonCard.svelte';

	interface Props {
		job?: JobView;
		driveNames?: Record<string, string> | null;
		paused?: boolean;
		/** Review countdown duration (config manual_wait_seconds). Cosmetic — the
		 *  ripper owns the authoritative clock; this only drives the UI timer. */
		manualWaitSeconds?: number;
		onrefresh?: () => void;
		ondismiss?: () => void;
	}

	let { job, driveNames, paused = false, manualWaitSeconds = 60, onrefresh, ondismiss }: Props = $props();
	let driveName = $derived(job?.drive_id ? (driveNames?.[job.drive_id] ?? null) : null);

	// awaiting_review = the timed review gate (Start / countdown); other waiting
	// statuses (awaiting_user_id / ripped_awaiting_identify) are identify-only.
	let isReviewGate = $derived(job?.status === 'awaiting_review');
	let starting = $state(false);

	let data = $state<JobDetailView | null>(null);
	let initialLoading = $state(true);
	let showTitleSearch = $state(false);
	let showMusicSearch = $state(false);
	let showDiscInfo = $state(false);
	let showApplySession = $state(false);
	let cancelling = $state(false);
	let openSearchTrackIds = $state<Set<string>>(new Set());
	let savingTrackField = $state<string | null>(null);
	let errorMessage = $state<string | null>(null);

	// Disc-set info (multi-disc). Wired to PATCH /jobs/{id} (disc_number/disc_total).
	let discNumberInput = $state('');
	let discTotalInput = $state('');
	let savingDiscInfo = $state(false);

	let tracks = $derived<TrackView[]>(data?.tracks ?? []);

	// v3 classifies disc kind via disc_type. cd → music, data → data, the rest
	// are video.
	let isMusic = $derived(job?.disc_type === 'cd');
	let isData = $derived(job?.disc_type === 'data');
	let isVideo = $derived(!isMusic && !isData);
	// Review has been applied once the job is identified — offer a non-destructive
	// "Done" to clear the card (the disc proceeds; Cancel still abandons).
	let isIdentified = $derived((data?.job?.status ?? job?.status)?.toLowerCase() === 'identified');

	// Prefer the reloaded detail (fresh after an apply/resolve) over the list-level
	// `job` prop, so the poster/title update immediately without a full dashboard
	// refresh. Falls back to the prop before the first detail load. Only read
	// inside the `{#if !job}{:else}` branch, where `job` is guaranteed defined.
	let displayJob = $derived((data?.job ?? job) as JobView);

	async function loadDetail() {
		if (!job) return;
		try {
			data = await fetchJob(job.id);
			// Seed disc-set inputs from the loaded job (empty = unset).
			discNumberInput = data?.job.disc_number != null ? String(data.job.disc_number) : '';
			discTotalInput = data?.job.disc_total != null ? String(data.job.disc_total) : '';
		} catch {
			data = null;
		} finally {
			initialLoading = false;
		}
	}

	async function saveDiscInfo() {
		if (!job) return;
		savingDiscInfo = true;
		errorMessage = null;
		// bind:value on a number input can yield a number; coerce before trim.
		const parse = (v: string | number) => {
			const t = String(v ?? '').trim();
			if (t === '') return null;
			const n = Number(t);
			return Number.isInteger(n) && n > 0 ? n : null;
		};
		try {
			await patchJob(job.id, { disc_number: parse(discNumberInput), disc_total: parse(discTotalInput) });
			onrefresh?.();
			loadDetail();
		} catch (e) {
			errorMessage = `Failed to save disc info: ${e instanceof Error ? e.message : 'Unknown error'}`;
		} finally {
			savingDiscInfo = false;
		}
	}

	async function handleTrackFieldUpdate(trackId: string, field: 'episode_number' | 'episode_name' | 'excluded', value: number | string | boolean | null) {
		if (!job) return;
		savingTrackField = `${trackId}-${field}`;
		errorMessage = null;
		try {
			await updateTrack(job.id, trackId, { [field]: value });
			loadDetail();
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

	function handleTitleApply() {
		onrefresh?.();
		loadDetail();
	}

	function handleSessionApplied() {
		showApplySession = false;
		onrefresh?.();
		loadDetail();
	}

	async function handleCancel() {
		if (!job) return;
		cancelling = true;
		try {
			await abandonJob(job.id);
		} catch {
			// still dismiss — next refresh will reconcile
		} finally {
			cancelling = false;
			ondismiss?.();
			onrefresh?.();
		}
	}

	async function handleStart() {
		if (!job) return;
		starting = true;
		errorMessage = null;
		try {
			await startWaitingJob(job.id);
			ondismiss?.();
			onrefresh?.();
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : 'Failed to start the rip';
		} finally {
			starting = false;
		}
	}

	function handleTrackTitleApply(trackId?: string) {
		if (trackId != null) {
			openSearchTrackIds = new Set([...openSearchTrackIds].filter((id) => id !== trackId));
		} else {
			openSearchTrackIds = new Set();
		}
		onrefresh?.();
		loadDetail();
	}

	function toggleTrackSearch(trackId: string) {
		const next = new Set(openSearchTrackIds);
		if (next.has(trackId)) next.delete(trackId);
		else next.add(trackId);
		openSearchTrackIds = next;
	}

	function toggleSection(section: 'title' | 'music' | 'discinfo') {
		const closeAll = () => { showTitleSearch = false; showMusicSearch = false; showDiscInfo = false; };
		if (section === 'title') {
			const next = !showTitleSearch; closeAll(); showTitleSearch = next;
		} else if (section === 'music') {
			const next = !showMusicSearch; closeAll(); showMusicSearch = next;
		} else {
			const next = !showDiscInfo; closeAll(); showDiscInfo = next;
		}
	}

	function formatLength(secs: number | null | undefined): string {
		if (!secs) return '--';
		const h = Math.floor(secs / 3600);
		const m = Math.floor((secs % 3600) / 60);
		const s = secs % 60;
		if (h > 0) return `${h}h ${m}m ${s}s`;
		return `${m}m ${s}s`;
	}

	onMount(() => {
		loadDetail();
	});

	const btnBase = 'rounded-lg px-3 py-1.5 text-sm font-medium transition-colors';
</script>

{#if !job}
	<SkeletonCard lines={4} />
{:else}
<div class="overflow-hidden rounded-lg ring-2 ring-primary bg-surface shadow-md dark:bg-surface-dark">
	<!-- Status bar -->
	<div class="flex items-center justify-between bg-primary px-4 py-1.5">
		<div class="flex items-center gap-2">
			<div class="h-2 w-2 animate-pulse rounded-full bg-white/80"></div>
			<span class="text-sm font-semibold text-on-primary">
				{isReviewGate ? 'Ready — Review & Start' : 'Awaiting Review'}
			</span>
		</div>
		<!-- Timed review gate: cosmetic countdown to auto-start (the ripper owns the
		     real clock). Shows paused when global ripping is paused. -->
		{#if isReviewGate && job.wait_start_time}
			<CountdownTimer startTime={job.wait_start_time} waitSeconds={manualWaitSeconds} {paused} inverted />
		{/if}
	</div>

	<!-- Header -->
	<div class="flex gap-4 p-4">
		<PosterImage url={displayJob.poster_url_manual ?? displayJob.poster_url} alt={displayJob.title ?? 'Poster'} class="h-24 shrink-0 rounded-sm object-cover {isMusic ? 'w-24' : 'w-16'}" />

		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-2">
				<h3 class="min-w-0 truncate text-lg font-semibold text-gray-900 dark:text-white">
					{displayJob.title || 'Untitled'}
					{#if displayJob.year}
						<span class="font-normal text-gray-500 dark:text-gray-400">({displayJob.year})</span>
					{/if}
				</h3>
			</div>
			<div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
				<span class="rounded-sm bg-primary/10 px-1.5 py-0.5 dark:bg-primary/15">{driveName ?? displayJob.drive_id}</span>
				<span class="inline-flex items-center gap-1 rounded-sm bg-primary/10 px-1.5 py-0.5 dark:bg-primary/15">
					<DiscTypeIcon disctype={displayJob.disc_type} size="h-3.5 w-3.5" />
					{discTypeLabel(displayJob.disc_type)}
				</span>
			</div>
		</div>
	</div>

	<!-- Error banner -->
	{#if errorMessage}
		<div class="flex items-center gap-2 border-t border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
			<span class="flex-1">{errorMessage}</span>
			<button onclick={() => (errorMessage = null)} class="shrink-0 text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300">&times;</button>
		</div>
	{/if}

	<!-- Action buttons -->
	<div class="flex items-center gap-1.5 border-t border-primary/20 bg-primary-light-bg/50 px-4 py-2 dark:border-primary/20 dark:bg-primary-light-bg-dark/10">
		{#if isVideo}
			<button
				onclick={() => toggleSection('title')}
				class="{btnBase} {showTitleSearch ? 'bg-primary text-on-primary' : 'bg-primary/5 text-gray-700 ring-1 ring-primary/25 hover:bg-primary/10 dark:bg-primary/10 dark:text-gray-200 dark:ring-primary/30 dark:hover:bg-primary/15'}"
			>
				Search
			</button>
		{/if}
		{#if isMusic}
			<button
				onclick={() => toggleSection('music')}
				class="{btnBase} {showMusicSearch ? 'bg-primary text-on-primary' : 'bg-primary/5 text-gray-700 ring-1 ring-primary/25 hover:bg-primary/10 dark:bg-primary/10 dark:text-gray-200 dark:ring-primary/30 dark:hover:bg-primary/15'}"
			>
				Search
			</button>
		{/if}
		<button
			onclick={() => toggleSection('discinfo')}
			class="{btnBase} {showDiscInfo ? 'bg-primary text-on-primary' : 'bg-primary/5 text-gray-700 ring-1 ring-primary/25 hover:bg-primary/10 dark:bg-primary/10 dark:text-gray-200 dark:ring-primary/30 dark:hover:bg-primary/15'}"
		>
			Disc info
		</button>
		<button
			onclick={() => (showApplySession = true)}
			class="{btnBase} bg-primary/5 text-gray-700 ring-1 ring-primary/25 hover:bg-primary/10 dark:bg-primary/10 dark:text-gray-200 dark:ring-primary/30 dark:hover:bg-primary/15"
		>
			Apply session
		</button>
		{#if isIdentified}
			<button
				onclick={() => ondismiss?.()}
				class="{btnBase} ml-auto bg-primary/5 text-gray-700 ring-1 ring-primary/25 hover:bg-primary/10 dark:bg-primary/10 dark:text-gray-200 dark:ring-primary/30 dark:hover:bg-primary/15"
			>
				Done
			</button>
		{/if}
		<button
			onclick={handleCancel}
			disabled={cancelling}
			class="{btnBase} {isIdentified ? '' : 'ml-auto'} text-red-600 ring-1 ring-red-300 hover:bg-red-50 disabled:opacity-50 dark:text-red-400 dark:ring-red-700 dark:hover:bg-red-900/20"
		>
			{cancelling ? 'Cancelling...' : 'Cancel'}
		</button>
		{#if isReviewGate}
			<button
				onclick={handleStart}
				disabled={starting}
				class="{btnBase} bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 dark:bg-green-500 dark:hover:bg-green-600"
			>
				{starting ? 'Starting...' : 'Start rip'}
			</button>
		{/if}
	</div>

	<!-- Tracks table -->
	<div class="border-t border-primary/20 p-4 dark:border-primary/20">
		{#if initialLoading}
			<p class="text-sm text-gray-400">Loading...</p>
		{:else if tracks.length > 0}
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
											<TrackTitleSearch jobId={job.id} {track} onapply={() => handleTrackTitleApply(track.id)} onclear={() => { onrefresh?.(); loadDetail(); }} onclose={() => toggleTrackSearch(track.id)} />
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

	<!-- Expanded sections -->
	{#if showTitleSearch && isVideo}
		<div class="border-t border-primary/20 p-4 dark:border-primary/20">
			<TitleSearch {job} onapply={handleTitleApply} />
		</div>
	{/if}

	{#if showMusicSearch && isMusic}
		<div class="border-t border-primary/20 p-4 dark:border-primary/20">
			<MusicSearch {job} discTracks={tracks} onapply={handleTitleApply} />
		</div>
	{/if}

	{#if showDiscInfo}
		<div class="border-t border-primary/20 p-4 dark:border-primary/20">
			<h4 class="mb-1 text-sm font-semibold text-gray-700 dark:text-gray-300">Disc set</h4>
			<p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
				For multi-disc sets (box sets, TV seasons), set this disc's position. Leave blank for a single disc.
			</p>
			<div class="flex flex-wrap items-end gap-3">
				<div class="flex flex-col gap-1">
					<label for="disc-number-{job.id}" class="text-xs font-medium text-gray-600 dark:text-gray-300">Disc number</label>
					<input
						id="disc-number-{job.id}"
						type="number"
						min="1"
						bind:value={discNumberInput}
						placeholder="—"
						disabled={savingDiscInfo}
						class="w-24 rounded-md border border-primary/25 bg-primary/5 px-2 py-1.5 text-sm text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-50 dark:border-primary/30 dark:bg-primary/10 dark:text-white"
					/>
				</div>
				<span class="pb-2 text-sm text-gray-400">of</span>
				<div class="flex flex-col gap-1">
					<label for="disc-total-{job.id}" class="text-xs font-medium text-gray-600 dark:text-gray-300">Disc total</label>
					<input
						id="disc-total-{job.id}"
						type="number"
						min="1"
						bind:value={discTotalInput}
						placeholder="—"
						disabled={savingDiscInfo}
						class="w-24 rounded-md border border-primary/25 bg-primary/5 px-2 py-1.5 text-sm text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-50 dark:border-primary/30 dark:bg-primary/10 dark:text-white"
					/>
				</div>
				<button
					onclick={saveDiscInfo}
					disabled={savingDiscInfo}
					class="{btnBase} bg-primary text-on-primary hover:bg-primary-hover disabled:opacity-50"
				>
					{savingDiscInfo ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	{/if}
</div>

{#if showApplySession}
	<ApplySessionDialog {job} onclose={() => (showApplySession = false)} onapplied={handleSessionApplied} />
{/if}
{/if}
