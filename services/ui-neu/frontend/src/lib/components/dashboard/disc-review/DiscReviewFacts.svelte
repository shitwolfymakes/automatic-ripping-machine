<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import type { JobMetadata } from '$lib/jobs/metadata';
	import type { EpisodeStatus } from '$lib/episodes/status';
	import { isIdentifyMiss, missReason } from '$lib/jobs/review';
	import {
		discFactsLine,
		episodeMatchingDetail,
		matchDetailLine,
		matchProviderLabel,
		type SourceRow
	} from '$lib/jobs/review-card';

	interface Props {
		/** The job the card shows (the loaded detail's, else the list's). */
		job: JobView;
		/** The job's metadata, read once by the card. */
		jobMeta: JobMetadata;
		/** Whether the disc is a video disc. */
		isVideo: boolean;
		/** Whether the card matches episodes (a TV video disc). */
		isTv: boolean;
		/** Whether the disc is an audio CD. */
		isMusic: boolean;
		/** Whether the disc already ripped and awaits a transcode session. */
		isPostRip: boolean;
		/** The Episodes row's state; null hides the row. */
		episodeRow: EpisodeStatus | null;
		/** The Source row's label and value. */
		sourceRow: SourceRow;
		/** The Session row's text; null hides the row. */
		appliedSession: string | null;
		/** Called by the Season row's "Season not set" link. */
		onopenseason: () => void;
		/** Called by the Episodes row's links. */
		onopenepisodes: () => void;
	}

	let {
		job,
		jobMeta,
		isVideo,
		isTv,
		isMusic,
		isPostRip,
		episodeRow,
		sourceRow,
		appliedSession,
		onopenseason,
		onopenepisodes
	}: Props = $props();

	let missLine = $derived(missReason(job));
	// A missed identify's title is the disc's own, so it is not a match yet.
	let isMiss = $derived(isIdentifyMiss(job));
	let matchDetail = $derived(matchDetailLine(job, isTv, jobMeta.video_type));
	let showProvider = $derived(matchProviderLabel(job));
	let discLine = $derived(discFactsLine(job, jobMeta.titleCount));
</script>

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
				{:else if isTv ? job.has_series : !!job.title?.trim() && !isMiss}
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
					<button type="button" class="disc-review-widget-link" onclick={onopenseason}>Season not set</button>
				{/if}
			</dd>
		</div>
	{/if}
	{#if episodeRow}
		<div class="disc-review-widget-row">
			<dt>Episodes</dt>
			<dd data-testid="episode-status" data-state={episodeRow.state}>
				{#if episodeRow.state === 'matched'}
					<button type="button" class="disc-review-widget-link" onclick={onopenepisodes}
						>Episodes matched{episodeRow.source ? ` from ${episodeRow.source}` : ''}</button
					>
				{:else if episodeRow.state === 'guess'}
					<span class="disc-review-widget-attention">Episodes placed, a guess</span><span
						class="disc-review-widget-muted">,</span
					>
					<button type="button" class="disc-review-widget-link" onclick={onopenepisodes}>Review</button>
				{:else if episodeRow.state === 'attention'}
					<span class="disc-review-widget-attention">Episodes need attention</span
					>{#if episodeRow.unmatched && episodeRow.total}<span class="disc-review-widget-muted"
							>, {episodeRow.unmatched} of {episodeRow.total} titles unmatched</span
						>{/if}<span class="disc-review-widget-muted">,</span>
					<button type="button" class="disc-review-widget-link" onclick={onopenepisodes}>Review</button>
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
			<span class="disc-review-widget-value disc-review-widget-source" title={sourceRow.value}>{sourceRow.value}</span>
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

<style>
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
</style>
