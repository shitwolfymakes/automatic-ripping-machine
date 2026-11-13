<script lang="ts">
	import type { Snippet } from 'svelte';
	import InlineField from '$lib/components/InlineField.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import type { JobDetail } from '$lib/stores/job-detail.svelte';
	import type { JobView } from '$lib/types/api.gen';
	import { effectiveJobStatus } from '$lib/jobs/status';

	interface Props {
		job: JobView;
		jobDetail: JobDetail;
		onsavetitle: (raw: string) => Promise<void>;
		children: Snippet;
	}

	let { job, jobDetail, onsavetitle, children }: Props = $props();
</script>

<div class="flex flex-wrap items-center gap-2 job-detail-title-bar">
	<h1 class="job-detail-title">
		<InlineField
			label="Title"
			value={job.title || 'Untitled'}
			canEdit={$isAdmin && jobDetail.canResolve}
			onsave={(raw) => onsavetitle(raw)}
		/>
	</h1>
	{#if job.year}
		<span class="job-detail-year">({job.year})</span>
	{/if}
	<StatusBadge status={effectiveJobStatus(job)} />
	{#if jobDetail.isVideoDisc && !$isAdmin}
		<span class="badge" data-testid="media-type-text">{job.media_type === 'tv' ? 'TV' : 'Movie'}</span>
	{/if}
	{#if jobDetail.jobMeta.imdb_id && !jobDetail.isCdDisc}
		<a
			href="https://www.imdb.com/title/{jobDetail.jobMeta.imdb_id}"
			target="_blank"
			rel="noopener noreferrer"
			class="badge badge-imdb job-detail-imdb-badge">IMDb</a
		>
	{/if}
	{#if jobDetail.jobMeta.multi_title}
		<span class="badge badge-sm job-detail-multi-title-badge">Multi-Title</span>
	{/if}
	{#if jobDetail.jobMeta.source_type === 'iso'}
		<span class="job-detail-source-badge">ISO</span>
	{:else if jobDetail.jobMeta.source_type === 'folder'}
		<span class="job-detail-source-badge">Folder</span>
	{/if}

	<!-- Action buttons pushed right -->
	{@render children()}
</div>

<style>
	.job-detail-title-bar {
		border-bottom: 1px solid var(--color-border);
		padding: 0.75rem 1.25rem;
	}
	.job-detail-title {
		font-size: 1.25rem;
		line-height: 1.75rem;
		font-weight: 700;
		color: var(--color-text);
	}
	.job-detail-year {
		font-size: 1rem;
		line-height: 1.5rem;
		color: var(--color-text-faint);
	}
	.job-detail-imdb-badge {
		border-radius: 9999px;
		padding: 0.125rem 0.625rem;
		font-size: 10px;
	}
	.job-detail-multi-title-badge {
		border-radius: 9999px;
		text-transform: uppercase;
		background: color-mix(in srgb, var(--color-accent-3) 15%, transparent);
		color: var(--color-accent-3);
	}
	.job-detail-source-badge {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.5rem;
		font-size: 10px;
		font-weight: 500;
		background: color-mix(in srgb, var(--color-accent-3) 15%, transparent);
		color: var(--color-accent-3);
	}
</style>
