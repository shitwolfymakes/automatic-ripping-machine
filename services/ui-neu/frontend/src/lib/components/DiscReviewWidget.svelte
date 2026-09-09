<script lang="ts">
	import { onMount } from 'svelte';
	import type { JobView, JobDetailView, TrackView, ScanResult, SessionView } from '$lib/types/api.gen';
	import { abandonJob, fetchJob, startWaitingJob, pauseWaitingJob, resolveJob } from '$lib/api/jobs';
	import { fetchSessions } from '$lib/api/sessions';
	import { readJobMetadata, videoTypeLabel } from '$lib/utils/job-fields';
	import { driveLabel } from '$lib/utils/drive-name';
	import { reviewPhaseBadge } from '$lib/utils/job-status';
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
	import { isAdmin } from '$lib/stores/auth';

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
	let scanTitles = $derived(
		((data?.job?.metadata_json?.scan_result as ScanResult | undefined)?.titles) ?? []
	);

	// v3 classifies disc kind via disc_type. cd → music, data → data, the rest
	// are video.
	let isMusic = $derived(job?.disc_type === 'cd');
	let isData = $derived(job?.disc_type === 'data');
	let isVideo = $derived(!isMusic && !isData);
	// "Start rip" (save + start) stays available through the whole review phase —
	// including after a metadata Save has identified the disc — so saving never
	// removes the way to start the rip. Cancel still abandons.
	let canStart = $derived(
		['awaiting_user_id', 'awaiting_review', 'ripped_awaiting_identify', 'identified'].includes(
			(data?.job?.status ?? job?.status) ?? ''
		)
	);
	// Post-rip phase: the disc already ripped and is awaiting a transcode session.
	// The card comes back so the operator can apply a session (which starts the
	// transcode) and fix metadata. No countdown, and "Apply session" is primary.
	let isPostRip = $derived(['ripped', 'ripped_partial'].includes((data?.job?.status ?? job?.status) ?? ''));

	// Prefer the reloaded detail (fresh after an apply/resolve) over the list-level
	// `job` prop, so the poster/title update immediately without a full dashboard
	// refresh. Falls back to the prop before the first detail load. Only read
	// inside the `{#if !job}{:else}` branch, where `job` is guaranteed defined.
	let displayJob = $derived((data?.job ?? job) as JobView);

	let sessions = $state<SessionView[]>([]);
	let sessionNameById = $derived(new Map(sessions.map((s) => [s.id, s.name])));

	let jobMeta = $derived(readJobMetadata(displayJob.metadata_json));

	function shortId(id: string): string {
		return id.length > 15 ? `${id.slice(0, 15)}...` : id;
	}
	let appliedSession = $derived(
		jobMeta.pending_session_id
			? (sessionNameById.get(jobMeta.pending_session_id) ?? shortId(jobMeta.pending_session_id))
			: null
	);

	// Header phase pill. For a post-rip job that already HAS a session pending but
	// is missing a title, switch the label to NEEDS TITLE; otherwise use the
	// helper's default (NEEDS SESSION for post-rip).
	let phaseBadge = $derived.by(() => {
		const b = reviewPhaseBadge(displayJob);
		if (isPostRip && jobMeta.pending_session_id && !(displayJob.title?.trim())) {
			return { ...b, label: 'RIPPED | NEEDS TITLE' };
		}
		return b;
	});
	// Clean fallback for an unidentified disc: prefer the title, then a
	// generic phrase — never the bare "Untitled".
	let displayTitle = $derived(
		displayJob.title?.trim() || 'Unidentified disc'
	);

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
			errorMessage = 'A title is required to start. Open Info or Search to set one.';
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

	async function loadSessions() {
		try {
			sessions = await fetchSessions();
		} catch {
			sessions = [];
		}
	}

	onMount(() => {
		loadDetail();
		loadSessions();
	});


</script>

{#if !job}
	<SkeletonCard lines={4} />
{:else}
<div class="disc-review-widget">
	<!-- Status bar -->
	<div class="disc-review-widget-status-bar">
		<div class="flex items-center gap-2">
			<div class="disc-review-widget-status-dot"></div>
			<span class="disc-review-widget-status-label">
				{isReviewGate ? 'Ready: Review & Start' : isPostRip ? 'Ripped: Apply Session' : 'Awaiting Review'}
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
				onpause={!$isAdmin || paused || pauseBusy ? undefined : () => handlePauseToggle(true)}
				onresume={!$isAdmin || paused || pauseBusy ? undefined : () => handlePauseToggle(false)}
			/>
		{/if}
	</div>

	<!-- Header -->
	<div class="flex gap-4 p-4">
		<PosterImage url={displayJob.poster_url_manual ?? displayJob.poster_url} alt={displayJob.title ?? 'Poster'} class="disc-review-widget-poster {isMusic ? 'disc-review-widget-poster-square' : ''}" />

		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-2">
				<span class="disc-review-widget-phase-badge" style:--phase-accent={phaseBadge.accent}>{phaseBadge.label}</span>
				<h3 class="min-w-0 truncate disc-review-widget-title">
					{displayTitle}
					{#if displayJob.year}
						<span class="disc-review-widget-title-year">({displayJob.year})</span>
					{/if}
				</h3>
			</div>
			<div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 disc-review-widget-meta">
				<span class="disc-review-widget-pill">{driveLabel(displayJob.drive_id, driveNames)}</span>
				<span class="inline-flex items-center gap-1 disc-review-widget-pill">
					<DiscTypeIcon disctype={displayJob.disc_type} size="h-3.5 w-3.5" />
					{discTypeLabel(displayJob.disc_type)}
				</span>
				{#if jobMeta.video_type}
					<span class="disc-review-widget-pill">{videoTypeLabel(jobMeta.video_type)}</span>
				{/if}
				{#if displayJob.disc_number != null}
					<span class="disc-review-widget-pill">Disc {displayJob.disc_number}{#if displayJob.disc_total != null}/{displayJob.disc_total}{/if}</span>
				{/if}
				{#if jobMeta.titleCount != null && jobMeta.titleCount > 0}
					<span class="disc-review-widget-pill">{jobMeta.titleCount} titles</span>
				{/if}
				{#if jobMeta.season}
					<span class="disc-review-widget-pill">S{jobMeta.season}</span>
				{/if}
				{#if jobMeta.imdb_id && !isMusic}
					<a href="https://www.imdb.com/title/{jobMeta.imdb_id}" target="_blank" rel="noopener noreferrer" class="badge badge-imdb">IMDb</a>
				{/if}
				{#if jobMeta.artist}
					<span class="disc-review-widget-pill">{jobMeta.artist}</span>
				{/if}
				{#if jobMeta.album}
					<span class="disc-review-widget-pill">{jobMeta.album}</span>
				{/if}
				{#if appliedSession}
					<span class="disc-review-widget-session-pill">Session: {appliedSession}</span>
				{/if}
			</div>
		</div>
	</div>

	<!-- Error banner -->
	{#if errorMessage}
		<div class="alert alert-danger disc-review-widget-error">
			<span class="flex-1">{errorMessage}</span>
			<button onclick={() => (errorMessage = null)} class="shrink-0 disc-review-widget-error-dismiss">&times;</button>
		</div>
	{/if}

	<!-- Action buttons -->
	<div class="flex items-center gap-1.5 disc-review-widget-actions">
		<button
			onclick={() => toggleSection('info')}
			class="btn disc-review-widget-action-btn"
			aria-pressed={showInfo}
		>
			Info
		</button>
		{#if isVideo}
			<button onclick={() => toggleSection('title')} class="btn disc-review-widget-action-btn" aria-pressed={showTitleSearch}>Search</button>
		{/if}
		{#if isMusic}
			<button onclick={() => toggleSection('music')} class="btn disc-review-widget-action-btn" aria-pressed={showMusicSearch}>Search</button>
		{/if}
		{#if $isAdmin}
			<button onclick={() => (showApplySession = true)} class="btn {isPostRip ? 'disc-review-widget-success-btn' : 'disc-review-widget-action-btn'}">{isPostRip ? 'Apply session & transcode' : 'Apply session'}</button>
		{/if}
		<a
			href="/jobs/{job.id}"
			class="btn disc-review-widget-action-btn"
		>
			View details
		</a>
		{#if $isAdmin}
			<button
				onclick={handleCancel}
				disabled={cancelling}
				class="btn btn-danger ml-auto"
			>
				{cancelling ? 'Cancelling...' : 'Cancel'}
			</button>
		{/if}
		{#if canStart && $isAdmin}
			<button
				onclick={handleStartRip}
				disabled={starting}
				class="btn disc-review-widget-success-btn"
				title="Save the metadata and start ripping this disc"
			>
				{starting ? 'Starting...' : 'Start rip'}
			</button>
		{/if}
	</div>

	<!-- Expanded sections -->
	{#if showTitleSearch && isVideo}
		<div class="disc-review-widget-panel">
			<TitleSearch {job} onapply={handleTitleApply} />
		</div>
	{/if}

	{#if showMusicSearch && isMusic}
		<div class="disc-review-widget-panel">
			<MusicSearch {job} discTracks={tracks} onapply={handleTitleApply} />
		</div>
	{/if}

	{#if showInfo}
		<JobInfoForm {job} onrefresh={() => { onrefresh?.(); loadDetail(); }} />
		<!-- Scanned titles (pre-rip) / tracks (post-rip) live at the bottom of the Info tab -->
		<div class="disc-review-widget-panel-top">
			{#if initialLoading}
				<p class="disc-review-widget-loading">Loading...</p>
			{:else}
				<ReviewTracksTable {job} {tracks} {scanTitles} {isVideo} {isMusic} onrefresh={() => { onrefresh?.(); loadDetail(); }} />
			{/if}
		</div>
	{/if}
</div>

{#if showApplySession}
	<ApplySessionDialog {job} onclose={() => (showApplySession = false)} onapplied={handleSessionApplied} />
{/if}
{/if}

<style>
	/* the widget's own emphasis ring (ring-2 ring-primary) is a stronger
	   highlight than card's default 1px border, since this card is meant to
	   grab attention on the dashboard */
	.disc-review-widget { overflow: hidden; border-radius: var(--radius-lg); box-shadow: 0 0 0 2px var(--color-primary), var(--shadow-2); background: var(--color-surface); }
	.disc-review-widget-status-bar { display: flex; align-items: center; justify-content: space-between; background: var(--color-primary); padding: 0.375rem 1rem; }
	.disc-review-widget-status-dot { height: 0.5rem; width: 0.5rem; flex-shrink: 0; border-radius: 9999px; background: color-mix(in srgb, var(--color-on-primary) 80%, transparent); animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
	@keyframes pulse { 50% { opacity: 0.5; } }
	/* :global: forwarded through PosterImage's class prop onto its own img */
	:global(.disc-review-widget-poster) { height: 6rem; width: 4rem; flex-shrink: 0; border-radius: var(--radius-sm); object-fit: cover; }
	/* :global: forwarded through PosterImage's class prop */
	:global(.disc-review-widget-poster-square) { width: 6rem; }
	.disc-review-widget-status-label { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-on-primary); }
	.disc-review-widget-phase-badge { flex-shrink: 0; border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-on-primary); background: var(--phase-accent); }
	.disc-review-widget-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	.disc-review-widget-title-year { font-weight: 400; color: var(--color-text-muted); }
	.disc-review-widget-loading { padding: 1rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-faint); }
	.disc-review-widget-meta { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.disc-review-widget-pill { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; background: var(--color-primary-tint-2); }
	.disc-review-widget-session-pill { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-weight: 500; background: var(--color-primary-tint-3); color: var(--color-primary-text); }
	.disc-review-widget-error { display: flex; align-items: center; gap: 0.5rem; border-top: 1px solid color-mix(in srgb, var(--color-danger) 30%, transparent); border-radius: 0; padding: 0.5rem 1rem; }
	.disc-review-widget-error-dismiss { color: var(--color-danger); }
	.disc-review-widget-error-dismiss:hover { color: var(--color-on-danger-soft); }
	.disc-review-widget-actions { border-top: 1px solid var(--color-border); background: color-mix(in srgb, var(--color-primary-tint-3) 50%, transparent); padding: 0.5rem 1rem; }
	/* the original action buttons were px-3 py-1.5 text-sm (0.75rem/0.375rem,
	   0.875rem) - between .btn's default and .btn-sm, so neither preset
	   alone matches; override both on the row's own .btn children. The
	   original border was a ring (box-shadow, no layout space), not .btn's
	   real 1px border, so border:0 here keeps the height exact. */
	.disc-review-widget-actions .btn { min-height: auto; padding: 0.375rem 0.75rem; font-size: 0.875rem; line-height: 1.25rem; border: 0; }
	/* the original inactive action button was a tinted fill (bg-primary/5,
	   ring-primary/25, text-gray-700), not .btn's bare-outline default
	   (transparent background, primary-text colour) */
	.disc-review-widget-action-btn { background: var(--color-primary-tint-1); box-shadow: 0 0 0 1px var(--color-border); color: var(--color-text-secondary); }
	.disc-review-widget-action-btn:hover { background: var(--color-primary-tint-2); }
	.disc-review-widget-action-btn[aria-pressed="true"] { background: var(--color-primary); color: var(--color-on-primary); box-shadow: none; }
	.disc-review-widget-success-btn { background: var(--color-success); color: var(--color-on-primary); }
	.disc-review-widget-success-btn:hover { background: var(--color-success); filter: brightness(0.9); }
	/* Cancel keeps .btn-danger's tone but the original border was a ring too */
	.disc-review-widget-actions .btn-danger { box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-danger) 30%, transparent); }
	.disc-review-widget-panel { border-top: 1px solid var(--color-border); padding: 1rem; }
	.disc-review-widget-panel-top { border-top: 1px solid var(--color-border); }
</style>
