<script lang="ts">
	import { posterSrc, posterFallback } from '$lib/match/poster';
	import StatusBadge from '$lib/components/shared/StatusBadge.svelte';
	import TrackTitleSearch from '$lib/components/match/TrackTitleSearch.svelte';
	import { formatFps } from '$lib/transcode/fps';
	import { trackKindLabel, trackSizeLabel } from '$lib/jobs/track-fields';
	import { formatTrackLength } from '$lib/utils/format';
	import { isAdmin } from '$lib/stores/auth';
	import type { JobView, NamingPreviewItem, TrackView } from '$lib/types/api.gen';

	interface Props {
		job: JobView;
		track: TrackView;
		preview: NamingPreviewItem | undefined;
		tracksAreSeries: boolean;
		editing: boolean;
		ontoggleedit: () => void;
		oncloseedit: () => void;
		onexcludedchange: (trackId: string, excluded: boolean) => void;
		ontitleapplied: () => void;
	}

	let {
		job,
		track,
		preview,
		tracksAreSeries,
		editing,
		ontoggleedit,
		oncloseedit,
		onexcludedchange,
		ontitleapplied
	}: Props = $props();
</script>

<tr class="table-row" data-disabled={track.excluded}>
	<td class="table-cell" data-label="#">{track.index}</td>
	<td class="table-cell job-detail-track-kind" data-label="Kind">{trackKindLabel(track.kind)}</td>
	<td
		class="table-cell {$isAdmin ? 'job-detail-track-title-cell' : ''}"
		data-label="Title"
		onclick={$isAdmin ? ontoggleedit : undefined}
	>
		{#if track.title}
			<div class="flex items-center gap-1.5">
				{#if track.poster_url}
					<img
						data-poster
						src={posterSrc(track.poster_url)}
						alt=""
						class="job-detail-track-poster"
						onerror={posterFallback}
					/>
				{/if}
				<div>
					<span class="job-detail-track-title job-detail-track-title-strong">{track.title}</span>
					{#if track.year}
						<span class="job-detail-track-year"> ({track.year})</span>
					{/if}
					<div class="mt-0.5 flex flex-wrap items-center gap-1">
						{#if track.imdb_id}
							<a
								href="https://www.imdb.com/title/{track.imdb_id}"
								target="_blank"
								rel="noopener noreferrer"
								onclick={(e) => e.stopPropagation()}
								class="badge badge-imdb job-detail-track-imdb-badge">IMDb</a
							>
						{/if}
						{#if track.edition}
							<span class="job-detail-track-meta-pill">{track.edition}</span>
						{/if}
						{#if track.role}
							<span class="job-detail-track-meta-pill">{track.role}</span>
						{/if}
					</div>
				</div>
			</div>
		{:else}
			<span class="job-detail-track-untitled"
				>{job.title || 'Untitled'}{#if job.year}
					({job.year}){/if}</span
			>
		{/if}
	</td>
	{#if tracksAreSeries}
		<td class="table-cell" data-label="Episode">
			{#if preview?.output_name}
				<!-- A session names the track: the generated name is the episode. -->
				<span class="mono job-detail-track-generated">{preview.output_name}</span>
			{:else if track.episode_number != null}
				<span class="job-detail-track-title job-detail-track-title-strong">{track.episode_number}</span>
				{#if track.episode_name}
					<span class="ml-1.5 job-detail-track-episode-name">{track.episode_name}</span>
				{/if}
			{:else}
				<span class="job-detail-track-faint">-</span>
			{/if}
		</td>
	{/if}
	<td
		class="truncate table-cell mono job-detail-track-filename"
		data-label="Filename"
		title={preview?.output_name ?? ''}
	>
		{#if preview?.output_name}
			<span>{preview.output_name}</span>
			{#if track.custom_filename}
				<span class="ml-1 badge badge-sm badge-warning">custom</span>
			{/if}
		{:else}
			<span class="job-detail-track-faint">{track.excluded ? 'excluded' : '-'}</span>
		{/if}
	</td>
	<td class="table-cell" data-label="Length">
		{#if track.duration_seconds != null}
			{formatTrackLength(track.duration_seconds)}
		{:else if track.expected_duration_seconds != null}
			<span class="job-detail-track-faint">~{formatTrackLength(track.expected_duration_seconds)}</span>
		{:else}-{/if}
	</td>
	<td class="table-cell job-detail-track-kind" data-label="Size">{trackSizeLabel(track)}</td>
	<td class="table-cell" data-label="Include">
		{#if $isAdmin}
			<input
				type="checkbox"
				checked={!track.excluded}
				onchange={(e) => onexcludedchange(track.id, !(e.currentTarget as HTMLInputElement).checked)}
				title="Include this track in transcode output (the disc still rips in full)"
				class="job-detail-track-checkbox"
			/>
		{:else}
			<span class="job-detail-track-untitled">{track.excluded ? 'Excluded' : 'Included'}</span>
		{/if}
	</td>
	<!-- Rip outcome -->
	<td class="table-cell" data-label="Rip">
		<span class="flex items-center gap-1">
			<StatusBadge status={track.status} />
			{#if track.attempts > 1}
				<span class="job-detail-track-attempts" title="Rip attempts">x{track.attempts}</span>
			{/if}
		</span>
	</td>
	<!-- Transcode outcome (— when no transcode task yet) -->
	<td class="table-cell" data-label="Transcode">
		{#if track.transcode_status}
			<span class="flex items-center gap-1">
				<StatusBadge status={track.transcode_status} />
				{#if track.transcode_status === 'in_progress' && track.transcode_fps != null}
					<span class="job-detail-track-faint" title="Encoder frame rate"
						>{formatFps(track.transcode_fps, track.transcode_avg_fps)}</span
					>
				{/if}
			</span>
		{:else}
			<span class="job-detail-track-faint">-</span>
		{/if}
	</td>
</tr>
{#if track.status === 'failed' && track.last_error}
	<tr>
		<td colspan="99" class="table-cell job-detail-track-error" data-label="">
			<span class="job-detail-error-strong">Error:</span>
			{track.last_error}
		</td>
	</tr>
{/if}
{#if editing}
	<tr>
		<td colspan="99" class="table-cell" data-label="">
			<TrackTitleSearch
				jobId={job.id}
				{track}
				mediaType={job.media_type}
				onapply={ontitleapplied}
				onclose={oncloseedit}
			/>
		</td>
	</tr>
{/if}

<style>
	.job-detail-track-kind {
		color: var(--color-text-secondary);
	}
	.job-detail-track-title-cell {
		cursor: pointer;
	}
	.job-detail-track-title-cell:hover {
		background: var(--color-primary-tint-1);
	}
	.job-detail-track-poster {
		height: 2rem;
		width: 1.25rem;
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	.job-detail-track-title {
		color: var(--color-text);
	}
	.job-detail-track-title-strong {
		font-weight: 500;
	}
	.job-detail-error-strong {
		font-weight: 600;
	}
	.job-detail-track-year {
		color: var(--color-text-faint);
	}
	.job-detail-track-imdb-badge {
		border-radius: 9999px;
		padding: 0.125rem 0.375rem;
		font-size: 9px;
	}
	.job-detail-track-meta-pill {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		font-size: 9px;
		font-weight: 500;
		background: var(--color-primary-tint-2);
		color: var(--color-text-secondary);
	}
	.job-detail-track-untitled {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	.job-detail-track-episode-name {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	.job-detail-track-generated {
		font-size: 0.8125rem;
	}
	.job-detail-track-faint {
		color: var(--color-text-faint);
	}
	.job-detail-track-filename {
		max-width: 260px;
		color: var(--color-text-secondary);
	}
	.job-detail-track-checkbox {
		width: 1rem;
		height: 1rem;
		border-radius: var(--radius-sm);
		accent-color: var(--color-primary);
	}
	.job-detail-track-attempts {
		font-size: 10px;
		color: var(--color-text-faint);
	}
	.job-detail-track-error {
		background: var(--color-danger-soft);
		color: var(--color-on-danger-soft);
	}
</style>
