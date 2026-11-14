<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import type { JobDetail } from '$lib/stores/job-detail.svelte';
	import type { JobPanels } from '$lib/stores/job-panels.svelte';

	interface Props {
		job: JobView;
		jobDetail: JobDetail;
		panels: JobPanels;
	}

	let { job, jobDetail, panels }: Props = $props();
</script>

{#if jobDetail.isVideoDisc}
	<div class="flex job-detail-panel-toggle-bar">
		<button
			type="button"
			onclick={() => panels.toggle('title')}
			class="job-detail-panel-tab"
			aria-pressed={panels.active === 'title'}>Poster &amp; metadata search</button
		>
		{#if job.media_type === 'tv'}
			<button
				type="button"
				onclick={() => panels.toggle('episodes')}
				class="job-detail-panel-tab"
				aria-pressed={panels.active === 'episodes'}>Match Episodes</button
			>
		{/if}
	</div>
{:else if jobDetail.isCdDisc}
	<div class="flex job-detail-panel-toggle-bar">
		<button
			type="button"
			onclick={() => panels.toggle('music')}
			class="job-detail-panel-tab"
			aria-pressed={panels.active === 'music'}>Match CD</button
		>
	</div>
{/if}

<style>
	.job-detail-panel-toggle-bar {
		border-top: 1px solid var(--color-border);
		background: color-mix(in srgb, var(--color-surface) 50%, transparent);
	}
	.job-detail-panel-tab {
		flex: 1 1 0%;
		padding: 0.625rem 1rem;
		text-align: center;
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-text-muted);
		transition: color var(--motion-fast) var(--ease);
	}
	.job-detail-panel-tab:hover {
		color: var(--color-text-secondary);
	}
	.job-detail-panel-tab[aria-pressed='true'] {
		color: var(--color-primary);
		border-bottom: 2px solid var(--color-primary);
		background: var(--color-primary-tint-1);
	}
</style>
