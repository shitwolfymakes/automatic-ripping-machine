<script lang="ts">
	import { onMount } from 'svelte';
	import type { JobView, JobDetailView, TrackView } from '$lib/types/api.gen';
	import { abandonJob, fetchJob, startWaitingJob, pauseWaitingJob, resolveJob } from '$lib/api/jobs';
	import CountdownTimer from './CountdownTimer.svelte';
	import { discTypeLabel } from '$lib/utils/job-type';
	import PosterImage from './PosterImage.svelte';
	import TitleSearch from './TitleSearch.svelte';
	import MusicSearch from './MusicSearch.svelte';
	import ApplySessionDialog from './ApplySessionDialog.svelte';
	import DiscTypeIcon from './DiscTypeIcon.svelte';
	import SkeletonCard from './SkeletonCard.svelte';
	import JobInfoForm from './JobInfoForm.svelte';
	import ReviewTracksTable from './ReviewTracksTable.svelte';

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
	let pauseBusy = $state(false);
	// The countdown is frozen by the global pause OR this disc's own pause.
	let countdownPaused = $derived(paused || !!job?.manual_pause);

	let data = $state<JobDetailView | null>(null);
	let initialLoading = $state(true);
	let showInfo = $state(false);
	let showTitleSearch = $state(false);
	let showMusicSearch = $state(false);
	let showApplySession = $state(false);
	let cancelling = $state(false);
	let errorMessage = $state<string | null>(null);

	let tracks = $derived<TrackView[]>(data?.tracks ?? []);

	// v3 classifies disc kind via disc_type. cd → music, data → data, the rest
	// are video.
	let isMusic = $derived(job?.disc_type === 'cd');
	let isData = $derived(job?.disc_type === 'data');
	let isVideo = $derived(!isMusic && !isData);
	// Review has been applied once the job is identified — offer a non-destructive
	// "Done" to clear the card (the disc proceeds; Cancel still abandons).
	let isIdentified = $derived((data?.job?.status ?? job?.status)?.toLowerCase() === 'identified');

	// "Start rip" (save + start) is offered while the disc is still awaiting an
	// operator decision — awaiting_user_id / awaiting_review / ripped_awaiting_identify.
	// Not for already-identified or terminal jobs (Done/Apply session handle those).
	let canStart = $derived(
		['awaiting_user_id', 'awaiting_review', 'ripped_awaiting_identify'].includes(
			(data?.job?.status ?? job?.status) ?? ''
		)
	);

	// Prefer the reloaded detail (fresh after an apply/resolve) over the list-level
	// `job` prop, so the poster/title update immediately without a full dashboard
	// refresh. Falls back to the prop before the first detail load. Only read
	// inside the `{#if !job}{:else}` branch, where `job` is guaranteed defined.
	let displayJob = $derived((data?.job ?? job) as JobView);

	async function loadDetail() {
		if (!job) return;
		try {
			data = await fetchJob(job.id);
		} catch {
			data = null;
		} finally {
			initialLoading = false;
		}
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


	// Action-row "Start rip": save + start. Resolving the job's current identity
	// (title/year/disc, preferring the freshly-loaded detail) is the save — it
	// also unblocks the parked ripper for an awaiting_user_id disc. For an
	// awaiting_review disc the rip is held by the countdown, so additionally skip
	// it via rip-start-review. Then dismiss the card; the disc is on its way.
	async function handleStartRip() {
		if (!job) return;
		const j = data?.job ?? job;
		const startTitle = (j.title ?? '').trim();
		if (!startTitle) {
			errorMessage = 'A title is required to start — open Info or Search to set one.';
			return;
		}
		starting = true;
		errorMessage = null;
		try {
			await resolveJob(job.id, {
				title: startTitle,
				year: j.year ?? null,
				disc_number: j.disc_number ?? null,
				disc_total: j.disc_total ?? null,
				metadata: {}
			});
			if (isReviewGate) {
				await startWaitingJob(job.id);
			}
			ondismiss?.();
			onrefresh?.();
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : 'Failed to start the rip';
		} finally {
			starting = false;
		}
	}

	async function handlePauseToggle(paused: boolean) {
		if (!job) return;
		pauseBusy = true;
		errorMessage = null;
		try {
			await pauseWaitingJob(job.id, paused);
			onrefresh?.();
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : 'Failed to update pause';
		} finally {
			pauseBusy = false;
		}
	}

	function toggleSection(section: 'info' | 'title' | 'music') {
		const closeAll = () => { showInfo = false; showTitleSearch = false; showMusicSearch = false; };
		if (section === 'info') {
			const next = !showInfo; closeAll(); showInfo = next;
		} else if (section === 'title') {
			const next = !showTitleSearch; closeAll(); showTitleSearch = next;
		} else {
			const next = !showMusicSearch; closeAll(); showMusicSearch = next;
		}
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
		     real clock). Frozen by the global pause OR this disc's own pause. The
		     timer's pause/resume toggles THIS disc only (per-job manual_pause);
		     it's hidden while globally paused since one disc can't un-pause the
		     whole machine. -->
		{#if isReviewGate && job.wait_start_time}
			<CountdownTimer
				startTime={job.wait_start_time}
				waitSeconds={manualWaitSeconds}
				paused={countdownPaused}
				inverted
				onpause={paused || pauseBusy ? undefined : () => handlePauseToggle(true)}
				onresume={paused || pauseBusy ? undefined : () => handlePauseToggle(false)}
			/>
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
		<button
			onclick={() => toggleSection('info')}
			class="{btnBase} {showInfo ? 'bg-primary text-on-primary' : 'bg-primary/5 text-gray-700 ring-1 ring-primary/25 hover:bg-primary/10 dark:bg-primary/10 dark:text-gray-200 dark:ring-primary/30 dark:hover:bg-primary/15'}"
		>
			Info
		</button>
		{#if isVideo}
			<button onclick={() => toggleSection('title')} class="{btnBase} {showTitleSearch ? 'bg-primary text-on-primary' : 'bg-primary/5 text-gray-700 ring-1 ring-primary/25 hover:bg-primary/10 dark:bg-primary/10 dark:text-gray-200 dark:ring-primary/30 dark:hover:bg-primary/15'}">Search</button>
		{/if}
		{#if isMusic}
			<button onclick={() => toggleSection('music')} class="{btnBase} {showMusicSearch ? 'bg-primary text-on-primary' : 'bg-primary/5 text-gray-700 ring-1 ring-primary/25 hover:bg-primary/10 dark:bg-primary/10 dark:text-gray-200 dark:ring-primary/30 dark:hover:bg-primary/15'}">Search</button>
		{/if}
		<button onclick={() => (showApplySession = true)} class="{btnBase} bg-primary/5 text-gray-700 ring-1 ring-primary/25 hover:bg-primary/10 dark:bg-primary/10 dark:text-gray-200 dark:ring-primary/30 dark:hover:bg-primary/15">Apply session</button>
		{#if isIdentified}
			<button
				onclick={() => ondismiss?.()}
				class="{btnBase} ml-auto bg-primary/5 text-gray-700 ring-1 ring-primary/25 hover:bg-primary/10 dark:bg-primary/10 dark:text-gray-200 dark:ring-primary/30 dark:hover:bg-primary/15"
			>
				Done
			</button>
		{/if}
		{#if canStart}
			<button
				onclick={handleStartRip}
				disabled={starting}
				class="{btnBase} {isIdentified ? '' : 'ml-auto'} bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 dark:bg-green-500 dark:hover:bg-green-600"
				title="Save the metadata and start ripping this disc"
			>
				{starting ? 'Starting...' : 'Start rip'}
			</button>
		{/if}
		<button
			onclick={handleCancel}
			disabled={cancelling}
			class="{btnBase} {isIdentified || canStart ? '' : 'ml-auto'} text-red-600 ring-1 ring-red-300 hover:bg-red-50 disabled:opacity-50 dark:text-red-400 dark:ring-red-700 dark:hover:bg-red-900/20"
		>
			{cancelling ? 'Cancelling...' : 'Cancel'}
		</button>
	</div>

	<!-- Tracks table -->
	<div class="border-t border-primary/20 dark:border-primary/20">
		{#if initialLoading}
			<p class="p-4 text-sm text-gray-400">Loading...</p>
		{:else}
			<ReviewTracksTable {job} {tracks} {isVideo} {isMusic} onrefresh={() => { onrefresh?.(); loadDetail(); }} />
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

	{#if showInfo}
		<JobInfoForm {job} onrefresh={() => { onrefresh?.(); loadDetail(); }} />
	{/if}
</div>

{#if showApplySession}
	<ApplySessionDialog {job} onclose={() => (showApplySession = false)} onapplied={handleSessionApplied} />
{/if}
{/if}
