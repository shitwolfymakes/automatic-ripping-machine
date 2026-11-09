<script lang="ts">
	import { onMount } from 'svelte';
	import type { JobView, TrackView, ScanResult } from '$lib/types/api.gen';
	import { DiscReviewData } from '$lib/stores/discReviewData.svelte';
	import { DiscReviewJobActions } from '$lib/stores/discReviewJobActions.svelte';
	import { parkedSessionLine } from '$lib/utils/parked-session';
	import { readJobMetadata } from '$lib/utils/job-metadata';
	import { episodeStatus } from '$lib/utils/episode-status';
	import {
		identitySuggestionOf,
		isIdentifyMiss,
		missReason,
		previouslyRippedJobId,
		reviewPhaseBadge
	} from '$lib/utils/job-review';
	import {
		appliedSessionName,
		discFactsLine,
		episodeMatchingDetail,
		matchDetailLine,
		matchProviderLabel,
		reviewSourceRow,
		reviewStatusLabel
	} from '$lib/utils/review-card';
	import DiscReviewStatusBar from './disc-review/DiscReviewStatusBar.svelte';
	import PreviouslyRippedNotice from './disc-review/PreviouslyRippedNotice.svelte';
	import PosterImage from './PosterImage.svelte';
	import TitleSearch from './TitleSearch.svelte';
	import MusicSearch from './MusicSearch.svelte';
	import ApplySessionDialog from './ApplySessionDialog.svelte';
	import ConfirmDialog from './ConfirmDialog.svelte';
	import SkeletonCard from './SkeletonCard.svelte';
	import JobInfoForm from './JobInfoForm.svelte';
	import ReviewTracksTable from './ReviewTracksTable.svelte';
	import IdentitySuggestionBanner from './IdentitySuggestionBanner.svelte';
	import MediaTypeSwitch from './episodes/MediaTypeSwitch.svelte';
	import EpisodeMatchPanel from './episodes/EpisodeMatchPanel.svelte';
	import { EpisodeMatching, watchEpisodeMatching } from '$lib/stores/episodeMatching.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import { ReviewSections } from '$lib/stores/reviewSections.svelte';

	interface Props {
		job?: JobView;
		driveNames?: Record<string, string> | null;
		/** drive id -> ISO file name, for the dashboard's currently-enrolled
		 *  virtual drives. Presence of `job.drive_id` here swaps the drive pill
		 *  for an ISO source chip and reroutes Cancel through cancelIsoRip. */
		isoSources?: Record<string, string> | null;
		/** drive id -> 'iso' / 'folder' for the same drives. */
		isoSourceKinds?: Record<string, 'iso' | 'folder'> | null;
		paused?: boolean;
		/** Review countdown duration (config manual_wait_seconds). Cosmetic — the
		 *  ripper owns the authoritative clock; this only drives the UI timer. */
		manualWaitSeconds?: number;
		onrefresh?: () => void;
		ondismiss?: () => void;
	}

	let {
		job,
		driveNames,
		isoSources,
		isoSourceKinds,
		paused = false,
		manualWaitSeconds = 60,
		onrefresh,
		ondismiss
	}: Props = $props();

	// awaiting_review = the timed review gate (Start / countdown); other waiting
	// statuses (awaiting_user_id / ripped_awaiting_identify) are identify-only.
	let isReviewGate = $derived(job?.status === 'awaiting_review');
	// The countdown is frozen by the global pause OR this disc's own pause.
	let countdownPaused = $derived(paused || !!job?.manual_pause);

	const reviewData = new DiscReviewData(() => job?.id);
	const sections = new ReviewSections();
	let episodePanel = $state<{ reload: () => Promise<void> } | undefined>(undefined);
	// "Matching episodes..." while the Backend re-matches after a series pick or a
	// flip to TV; job.identity_updated for this job (or a timeout) ends it.
	const matching = new EpisodeMatching();
	let showApplySession = $state(false);
	const actions = new DiscReviewJobActions({ dismiss: () => ondismiss?.(), refresh: () => onrefresh?.() });

	let tracks = $derived<TrackView[]>(reviewData.detail?.tracks ?? []);
	// Tracks whose episode or role the user set by hand (switching to Movie drops them).
	let handSetCount = $derived(
		tracks.filter((t) => ['episode_number', 'role'].some((k) => t.identity_provenance?.[k] === 'manual')).length
	);
	let scanTitles = $derived(
		(reviewData.detail?.job?.metadata_json?.scan_result as ScanResult | undefined)?.titles ?? []
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
			reviewData.detail?.job?.status ?? job?.status ?? ''
		)
	);
	// Post-rip phase: the disc already ripped and is awaiting a transcode session.
	// The card comes back so the operator can apply a session (which starts the
	// transcode) and fix metadata. No countdown, and "Apply session" is primary.
	let isPostRip = $derived(['ripped', 'ripped_partial'].includes(reviewData.detail?.job?.status ?? job?.status ?? ''));

	// Prefer the reloaded detail (fresh after an apply/resolve) over the list-level
	// `job` prop, so the poster/title update immediately without a full dashboard
	// refresh. Falls back to the prop before the first detail load. Only read
	// inside the `{#if !job}{:else}` branch, where `job` is guaranteed defined.
	let displayJob = $derived((reviewData.detail?.job ?? job) as JobView);
	// Episode matching is for TV video discs only, as on the job page.
	let isTv = $derived(isVideo && displayJob.media_type === 'tv');
	// The ripper holds the countdown while the episode placement is a guess; the card only says so.
	let countdownHeld = $derived(isTv && !!displayJob.episodes_unsure ? 'Held: episodes are a guess' : null);
	// An ISO rip's drive_id is a still-enrolled virtual drive; once the rip
	// completes that drive retires and drops out of isoSources, matching the
	// card leaving the dashboard.
	let isoName = $derived(displayJob.drive_id ? (isoSources?.[displayJob.drive_id] ?? null) : null);

	let jobMeta = $derived(readJobMetadata(displayJob.metadata_json, displayJob));

	// on_previously_ripped = hold: this disc matched an earlier rip. No
	// countdown runs; the operator chooses Rip again (Start) or Discard (Cancel).
	let previousId = $derived(isReviewGate ? previouslyRippedJobId(displayJob) : null);
	let previous = $derived(reviewData.detail?.previous_rip ?? null);
	// A confident match identify held for confirmation (auto-apply off).
	let suggestion = $derived(identitySuggestionOf(displayJob));
	let missLine = $derived(missReason(displayJob));
	let statusLabel = $derived(
		reviewStatusLabel({
			previouslyRipped: !!previousId,
			suggestion: !!suggestion,
			reviewGate: isReviewGate,
			postRip: isPostRip
		})
	);
	// A missed identify's title is the disc's own, so it is not a match yet.
	let isMiss = $derived(isIdentifyMiss(displayJob));
	// Null off a TV video disc and after the rip; the Episodes button follows it.
	let episodeRow = $derived(
		isTv ? episodeStatus(displayJob, reviewData.detail ? tracks : null, matching.active) : null
	);
	let matchDetail = $derived(matchDetailLine(displayJob, isTv, jobMeta.video_type));
	let showProvider = $derived(matchProviderLabel(displayJob));
	let discLine = $derived(discFactsLine(displayJob, jobMeta.titleCount));
	let sourceRow = $derived(reviewSourceRow(displayJob, isoName, isoSourceKinds, driveNames));
	let parkedLine = $derived(parkedSessionLine(displayJob, reviewData.sessionNames));
	let appliedSession = $derived(appliedSessionName(parkedLine, jobMeta.pending_session_id, reviewData.sessionNames));

	// Header phase pill. For a post-rip job that already HAS a session pending but
	// is missing a title, switch the label to NEEDS TITLE; otherwise use the
	// helper's default (NEEDS SESSION for post-rip).
	let phaseBadge = $derived.by(() => {
		const b = reviewPhaseBadge(displayJob);
		if (isPostRip && (jobMeta.pending_session_id || parkedLine) && !displayJob.title?.trim()) {
			return { ...b, label: 'RIPPED | NEEDS TITLE' };
		}
		return b;
	});
	// Clean fallback for an unidentified disc: prefer the title, then a
	// generic phrase — never the bare "Untitled".
	let displayTitle = $derived(displayJob.title?.trim() || 'Unidentified disc');

	function handleTitleApply() {
		onrefresh?.();
		reviewData.loadDetail();
	}

	// Picking a show in the match picker goes straight to episode matching.
	function handleSeriesApplied() {
		sections.open('episodes');
		matching.start();
		handleTitleApply();
	}

	function handleMediaTypeChanged(type: 'movie' | 'tv') {
		if (type === 'tv') {
			sections.open('episodes');
			matching.start();
		} else {
			matching.stop();
			sections.close('episodes');
		}
		handleTitleApply();
	}

	function handleSessionApplied() {
		showApplySession = false;
		onrefresh?.();
		reviewData.loadDetail();
	}

	onMount(() => {
		reviewData.loadDetail();
		reviewData.loadSessions();
		// The dashboard refreshes the job prop on every event; the card's own
		// detail (tracks) and the episode panel refresh only for this job.
		const offJobEvents = watchEpisodeMatching(
			() => job?.id,
			matching,
			async () => {
				await reviewData.loadDetail();
				await episodePanel?.reload();
			}
		);
		return () => {
			offJobEvents();
			matching.stop();
		};
	});
</script>

{#if !job}
	<SkeletonCard lines={4} />
{:else}
	<div class="disc-review-widget" data-source={isoName ? 'iso' : 'disc'}>
		<!-- Status bar -->
		<DiscReviewStatusBar
			label={statusLabel}
			waitStartTime={isReviewGate ? job.wait_start_time : null}
			waitSeconds={manualWaitSeconds}
			paused={countdownPaused || !!countdownHeld}
			held={countdownHeld}
			onpause={!$isAdmin || paused || actions.pauseBusy ? undefined : () => actions.setPaused(job, true)}
			onresume={!$isAdmin || paused || actions.pauseBusy ? undefined : () => actions.setPaused(job, false)}
		/>

		<!-- Body: poster, then the title row and one aligned, labeled row per fact. -->
		<div class="disc-review-widget-body">
			<PosterImage
				url={displayJob.poster_url_manual ?? displayJob.poster_url}
				alt={displayJob.title ?? 'Poster'}
				class="disc-review-widget-poster {isMusic ? 'disc-review-widget-poster-square' : ''}"
			/>

			<div class="disc-review-widget-content">
				<div class="disc-review-widget-title-row">
					<span class="disc-review-widget-phase-badge" style:--phase-accent={phaseBadge.accent}>{phaseBadge.label}</span
					>
					<h3 class="disc-review-widget-title" title={displayTitle}>
						{displayTitle}
						{#if displayJob.year}
							<span class="disc-review-widget-title-year">({displayJob.year})</span>
						{/if}
					</h3>
					<!-- The type picks what Search looks for, so the search row has no Movie/TV toggle of its own. -->
					{#if isVideo && $isAdmin}
						<div class="disc-review-widget-type">
							<MediaTypeSwitch job={displayJob} {handSetCount} onchanged={handleMediaTypeChanged} />
						</div>
					{/if}
				</div>

				<dl class="disc-review-widget-rows">
					{#if isVideo}
						<div class="disc-review-widget-row" data-testid="match-row">
							<dt>{isTv ? 'Show' : 'Match'}</dt>
							<dd>
								{#if jobMeta.imdb_id}
									<a
										href="https://www.imdb.com/title/{jobMeta.imdb_id}"
										target="_blank"
										rel="noopener noreferrer"
										class="badge badge-imdb">IMDb</a
									>
									<a
										href="https://www.imdb.com/title/{jobMeta.imdb_id}"
										target="_blank"
										rel="noopener noreferrer"
										class="disc-review-widget-ext-id">{jobMeta.imdb_id}</a
									>
									{#if matchDetail}<span class="disc-review-widget-muted">, {matchDetail}</span>{/if}
								{:else if isTv ? displayJob.has_series : !!displayJob.title?.trim() && !isMiss}
									<span>{showProvider ? `Matched on ${showProvider}` : 'Set by hand'}</span>
									{#if matchDetail}<span class="disc-review-widget-muted">, {matchDetail}</span>{/if}
								{:else}
									<span class="disc-review-widget-needs">{isTv ? 'Needs show' : 'No match'}</span><span
										class="disc-review-widget-muted"
										data-testid={missLine ? 'identify-miss-reason' : undefined}
										>, {missLine ?? `pick a ${isTv ? 'show' : 'title'} with Search`}</span
									>
								{/if}
							</dd>
						</div>
					{/if}
					{#if isTv && (jobMeta.season || !isPostRip)}
						<div class="disc-review-widget-row" data-testid="season-row">
							<dt>Season</dt>
							<dd>
								{#if jobMeta.season}
									<span>Season {Number(jobMeta.season)}</span>
								{:else}
									<button type="button" class="disc-review-widget-link" onclick={sections.openSeason}
										>Season not set</button
									>
								{/if}
							</dd>
						</div>
					{/if}
					{#if episodeRow}
						<div class="disc-review-widget-row">
							<dt>Episodes</dt>
							<dd data-testid="episode-status" data-state={episodeRow.state}>
								{#if episodeRow.state === 'matched'}
									<button type="button" class="disc-review-widget-link" onclick={() => sections.open('episodes')}
										>Episodes matched{episodeRow.source ? ` from ${episodeRow.source}` : ''}</button
									>
								{:else if episodeRow.state === 'guess'}
									<span class="disc-review-widget-attention">Episodes placed, a guess</span><span
										class="disc-review-widget-muted">,</span
									>
									<button type="button" class="disc-review-widget-link" onclick={() => sections.open('episodes')}
										>Review</button
									>
								{:else if episodeRow.state === 'attention'}
									<span class="disc-review-widget-attention">Episodes need attention</span
									>{#if episodeRow.unmatched && episodeRow.total}<span class="disc-review-widget-muted"
											>, {episodeRow.unmatched} of {episodeRow.total} titles unmatched</span
										>{/if}<span class="disc-review-widget-muted">,</span>
									<button type="button" class="disc-review-widget-link" onclick={() => sections.open('episodes')}
										>Review</button
									>
								{:else if episodeRow.state === 'matching'}
									{@const matchingDetail = episodeMatchingDetail(episodeRow)}
									<span class="disc-review-widget-matching">Matching episodes...</span>
									{#if matchingDetail}<span class="disc-review-widget-muted">{matchingDetail}</span>{/if}
								{:else}
									<span class="disc-review-widget-muted">Waiting for show</span>
								{/if}
							</dd>
						</div>
					{/if}
					{#if isMusic && missLine}
						<div class="disc-review-widget-row">
							<dt>Match</dt>
							<dd>
								<span class="disc-review-widget-needs">No match</span>
								<span class="disc-review-widget-muted" data-testid="identify-miss-reason">, {missLine}</span>
							</dd>
						</div>
					{/if}
					{#if jobMeta.artist}
						<div class="disc-review-widget-row">
							<dt>Artist</dt>
							<dd><span class="disc-review-widget-value" title={jobMeta.artist}>{jobMeta.artist}</span></dd>
						</div>
					{/if}
					{#if jobMeta.album}
						<div class="disc-review-widget-row">
							<dt>Album</dt>
							<dd><span class="disc-review-widget-value" title={jobMeta.album}>{jobMeta.album}</span></dd>
						</div>
					{/if}
					{#if discLine}
						<div class="disc-review-widget-row">
							<dt>Disc</dt>
							<dd>
								<span class="disc-review-widget-value" title={discLine}>{discLine}</span>
							</dd>
						</div>
					{/if}
					<div class="disc-review-widget-row">
						<dt>{sourceRow.label}</dt>
						<dd>
							<span class="disc-review-widget-value disc-review-widget-source" title={sourceRow.value}
								>{sourceRow.value}</span
							>
						</dd>
					</div>
					{#if appliedSession}
						<div class="disc-review-widget-row">
							<dt>Session</dt>
							<dd>
								<span class="disc-review-widget-value" title={appliedSession}>{appliedSession}</span>
							</dd>
						</div>
					{/if}
				</dl>
			</div>
		</div>

		{#if previousId}
			<PreviouslyRippedNotice {previous} loading={reviewData.initialLoading} />
		{/if}

		{#if suggestion}
			<div class="disc-review-widget-suggestion">
				<IdentitySuggestionBanner
					job={displayJob}
					canAct={$isAdmin}
					onaccepted={() => {
						reviewData.loadDetail();
						onrefresh?.();
					}}
					onsearch={() => {
						sections.open(isMusic ? 'music' : 'title');
					}}
				/>
			</div>
		{/if}

		<!-- Error banner -->
		{#if actions.errorMessage}
			<div class="alert alert-danger disc-review-widget-error">
				<span class="flex-1">{actions.errorMessage}</span>
				<button onclick={actions.dismissError} class="shrink-0 disc-review-widget-error-dismiss">&times;</button>
			</div>
		{/if}

		<!-- Action buttons -->
		<div class="flex flex-wrap items-center gap-1.5 disc-review-widget-actions">
			<button
				onclick={() => sections.toggle('info')}
				class="btn disc-review-widget-action-btn"
				aria-pressed={sections.isOpen('info')}
			>
				Info
			</button>
			{#if isVideo}
				<button
					onclick={() => sections.toggle('title')}
					class="btn disc-review-widget-action-btn"
					aria-pressed={sections.isOpen('title')}>Search</button
				>
			{/if}
			{#if episodeRow && (episodeRow.state !== 'matched' || sections.isOpen('episodes'))}
				<button
					onclick={() => sections.toggle('episodes')}
					class="btn disc-review-widget-action-btn"
					aria-pressed={sections.isOpen('episodes')}>Episodes</button
				>
			{/if}
			{#if isMusic}
				<button
					onclick={() => sections.toggle('music')}
					class="btn disc-review-widget-action-btn"
					aria-pressed={sections.isOpen('music')}>Search</button
				>
			{/if}
			{#if $isAdmin && displayJob.actions.can_apply}
				<button
					onclick={() => (showApplySession = true)}
					class="btn {isPostRip ? 'disc-review-widget-success-btn' : 'disc-review-widget-action-btn'}"
					>{isPostRip ? 'Apply session & transcode' : 'Apply session'}</button
				>
			{/if}
			<a href="/jobs/{job.id}" class="btn disc-review-widget-action-btn"> View details </a>
			{#if $isAdmin && displayJob.actions.can_abandon}
				<button
					onclick={() => actions.cancel(job, isoName)}
					disabled={actions.cancelling}
					class="btn btn-danger ml-auto"
					title={isoName ? 'Cancel the rip and remove the virtual drive' : undefined}
				>
					{actions.cancelling ? 'Cancelling...' : previousId ? 'Discard' : 'Cancel'}
				</button>
			{/if}
			{#if $isAdmin && displayJob.actions.can_delete}
				<button
					onclick={() => (actions.confirmDelete = true)}
					disabled={actions.deleting}
					class="btn btn-danger ml-auto"
				>
					{actions.deleting ? 'Deleting...' : 'Delete'}
				</button>
			{/if}
			{#if canStart && $isAdmin}
				<button
					onclick={() => actions.startRip(job, reviewData.detail?.job, () => isReviewGate)}
					disabled={actions.starting}
					class="btn disc-review-widget-success-btn"
					title={previousId ? 'Rip this disc again' : 'Save the metadata and start ripping this disc'}
				>
					{actions.starting ? 'Starting...' : previousId ? 'Rip again' : 'Start rip'}
				</button>
			{/if}
		</div>

		<!-- Expanded sections -->
		{#if sections.isOpen('title') && isVideo}
			<div class="disc-review-widget-panel">
				<TitleSearch
					job={displayJob}
					onapply={handleTitleApply}
					onseries={handleSeriesApplied}
					initialType={sections.titleInitialType}
				/>
			</div>
		{/if}

		{#if sections.isOpen('episodes') && isTv}
			<div class="disc-review-widget-panel" data-testid="episode-panel">
				<EpisodeMatchPanel
					bind:this={episodePanel}
					job={displayJob}
					{tracks}
					matching={matching.active}
					onchanged={() => reviewData.loadDetail()}
					onsearchseries={sections.searchSeries}
				/>
			</div>
		{/if}

		{#if sections.isOpen('music') && isMusic}
			<div class="disc-review-widget-panel">
				<MusicSearch {job} discTracks={tracks} onapply={handleTitleApply} />
			</div>
		{/if}

		{#if sections.isOpen('info')}
			<JobInfoForm
				{job}
				focusField={sections.infoFocus}
				onsaved={(c) => {
					if (isTv && (c.season || c.disc)) matching.start();
				}}
				onrefresh={() => {
					onrefresh?.();
					reviewData.loadDetail();
				}}
			/>
			<!-- Scanned titles (pre-rip) / tracks (post-rip) live at the bottom of the Info tab -->
			<div class="disc-review-widget-panel-top">
				{#if reviewData.initialLoading}
					<p class="disc-review-widget-loading">Loading...</p>
				{:else}
					<ReviewTracksTable
						{job}
						{tracks}
						{scanTitles}
						{isVideo}
						{isMusic}
						fileNames={reviewData.fileNames}
						onrefresh={() => {
							onrefresh?.();
							reviewData.loadDetail();
						}}
					/>
				{/if}
			</div>
		{/if}
	</div>

	{#if showApplySession}
		<ApplySessionDialog {job} onclose={() => (showApplySession = false)} onapplied={handleSessionApplied} />
	{/if}

	<ConfirmDialog
		open={actions.confirmDelete}
		title="Delete job"
		message="Delete this job? The raw files stay on disk. This cannot be undone."
		confirmLabel="Delete"
		variant="danger"
		onconfirm={() => actions.remove(job)}
		oncancel={() => (actions.confirmDelete = false)}
	/>
{/if}

<style>
	/* Attention comes from the tinted status bar (primary mixed into the
	   surface) rather than a solid primary fill and ring, so the card reads
	   as the same family as the other cards across every scheme. The parent
	   SectionFrame carries the emphasis for the section as a whole. */
	.disc-review-widget {
		overflow: hidden;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-2);
		background: var(--color-surface);
	}
	.disc-review-widget-suggestion {
		margin: 0 1rem 0.75rem;
	}
	/* :global: forwarded through PosterImage's class prop onto its own img */
	/* Same width as a CD's square cover, at the poster's 2:3. */
	:global(.disc-review-widget-poster) {
		height: 12.28125rem;
		width: 8.1875rem;
		flex-shrink: 0;
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.disc-review-widget-poster-square) {
		height: 8.1875rem;
	}
	@media (max-width: 639px) {
		.disc-review-widget-body {
			gap: 0.75rem;
			padding: 0.875rem;
		}
		/* :global: forwarded through PosterImage's class prop onto its own img */
		:global(.disc-review-widget-poster) {
			height: 7.875rem;
			width: 5.25rem;
		}
		/* :global: forwarded through PosterImage's class prop */
		:global(.disc-review-widget-poster-square) {
			height: 5.25rem;
		}
	}
	.disc-review-widget-phase-badge {
		flex-shrink: 0;
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.5rem;
		font-size: 0.75rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--color-on-primary);
		background: var(--phase-accent);
	}
	.disc-review-widget-body {
		display: flex;
		gap: 1.125rem;
		padding: 1.125rem;
	}
	.disc-review-widget-content {
		display: flex;
		min-width: 0;
		flex: 1;
		flex-direction: column;
	}
	/* Badge + title on the left, the TYPE toggle pinned right: the title
	   truncates, the toggle never shrinks. */
	.disc-review-widget-title-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.625rem;
		padding-bottom: 0.625rem;
	}
	/* flex-basis 8rem: below that the toggle wraps under the title rather
	   than squeezing it to nothing (phones). */
	.disc-review-widget-title {
		min-width: 0;
		flex: 1 1 8rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 1.375rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.disc-review-widget-type {
		flex-shrink: 0;
	}
	/* One aligned label column for every fact (a single grid, so the labels
	   share a width); each value stays on one line and ellipsizes. */
	.disc-review-widget-rows {
		display: grid;
		grid-template-columns: minmax(4.75rem, max-content) minmax(0, 1fr);
		margin: 0;
		border-top: 1px solid var(--color-border);
		font-size: 0.9375rem;
		line-height: 1.375rem;
	}
	.disc-review-widget-row {
		display: contents;
	}
	.disc-review-widget-row > dt,
	.disc-review-widget-row > dd {
		margin: 0;
		padding: 0.5625rem 0;
		border-bottom: 1px solid color-mix(in srgb, var(--color-border) 70%, transparent);
	}
	.disc-review-widget-row > dt {
		align-self: stretch;
		display: flex;
		align-items: center;
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--color-text-muted);
		/* the gutter is padding, not column-gap, so each divider runs unbroken */
		padding-right: 1.25rem;
	}
	.disc-review-widget-row > dd {
		display: flex;
		min-width: 0;
		align-items: center;
		gap: 0.375rem;
		overflow: hidden;
		white-space: nowrap;
		color: var(--color-text);
	}
	/* Every value part ellipsizes when the row runs out of room; the IMDb
	   pill keeps its size. */
	.disc-review-widget-row > dd > * {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.disc-review-widget-row > dd > .badge {
		flex-shrink: 0;
	}
	/* the muted trailing detail gives way long before the primary value */
	.disc-review-widget-row > dd > .disc-review-widget-muted {
		flex-shrink: 100;
	}
	.disc-review-widget-muted {
		color: var(--color-text-muted);
	}
	.disc-review-widget-source {
		color: var(--color-text-secondary);
	}
	.disc-review-widget-ext-id {
		font-family: var(--font-mono, ui-monospace, monospace);
		font-size: 0.875rem;
		color: var(--color-text-secondary);
	}
	.disc-review-widget-ext-id:hover {
		text-decoration: underline;
	}
	.disc-review-widget-needs,
	.disc-review-widget-attention {
		font-weight: 600;
		color: var(--color-warning);
	}
	.disc-review-widget-matching {
		font-weight: 600;
		color: var(--color-primary-text);
	}
	.disc-review-widget-link {
		padding: 0;
		border: 0;
		background: none;
		font: inherit;
		cursor: pointer;
		color: var(--color-primary);
		text-decoration: underline;
	}
	.disc-review-widget-title-year {
		font-weight: 400;
		color: var(--color-text-muted);
	}
	.disc-review-widget-loading {
		padding: 1rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-faint);
	}
	.disc-review-widget-error {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		border-top: 1px solid color-mix(in srgb, var(--color-danger) 30%, transparent);
		border-radius: 0;
		padding: 0.5rem 1rem;
	}
	.disc-review-widget-error-dismiss {
		color: var(--color-danger);
	}
	.disc-review-widget-error-dismiss:hover {
		color: var(--color-on-danger-soft);
	}
	.disc-review-widget-actions {
		border-top: 1px solid var(--color-border);
		background: color-mix(in srgb, var(--color-primary-tint-3) 50%, transparent);
		padding: 0.5rem 1rem;
	}
	/* the original action buttons were px-3 py-1.5 text-sm (0.75rem/0.375rem,
	   0.875rem) - between .btn's default and .btn-sm, so neither preset
	   alone matches; override both on the row's own .btn children. The
	   original border was a ring (box-shadow, no layout space), not .btn's
	   real 1px border, so border:0 here keeps the height exact. */
	.disc-review-widget-actions .btn {
		min-height: auto;
		padding: 0.375rem 0.75rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		border: 0;
	}
	/* the original inactive action button was a tinted fill (bg-primary/5,
	   ring-primary/25, text-gray-700), not .btn's bare-outline default
	   (transparent background, primary-text colour) */
	.disc-review-widget-action-btn {
		background: var(--color-primary-tint-1);
		box-shadow: 0 0 0 1px var(--color-border);
		color: var(--color-text-secondary);
	}
	.disc-review-widget-action-btn:hover {
		background: var(--color-primary-tint-2);
	}
	.disc-review-widget-action-btn[aria-pressed='true'] {
		background: var(--color-primary);
		color: var(--color-on-primary);
		box-shadow: none;
	}
	.disc-review-widget-success-btn {
		background: var(--color-success);
		color: var(--color-on-primary);
	}
	.disc-review-widget-success-btn:hover {
		background: var(--color-success);
		filter: brightness(0.9);
	}
	/* Cancel keeps .btn-danger's tone but the original border was a ring too */
	.disc-review-widget-actions .btn-danger {
		box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-danger) 30%, transparent);
	}
	.disc-review-widget-panel {
		border-top: 1px solid var(--color-border);
		padding: 1rem;
	}
	.disc-review-widget-panel-top {
		border-top: 1px solid var(--color-border);
	}
</style>
