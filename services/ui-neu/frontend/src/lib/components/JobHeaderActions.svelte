<script lang="ts">
	import JobActions from '$lib/components/JobActions.svelte';
	import MediaTypeSwitch from '$lib/components/episodes/MediaTypeSwitch.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import type { JobDetail } from '$lib/stores/jobDetail.svelte';
	import type { JobView } from '$lib/types/api.gen';

	// The two types the switch offers (a narrower set than the API's MediaType).
	type MediaType = 'movie' | 'tv';

	interface Props {
		job: JobView;
		jobDetail: JobDetail;
		onmediatypechanged: (type: MediaType) => void;
		onapply: () => void;
		ondelete: () => void;
	}

	let { job, jobDetail, onmediatypechanged, onapply, ondelete }: Props = $props();
</script>

<div class="flex flex-wrap items-center gap-2 ml-auto">
	<!-- The type is part of the identity, which is edited in place on the page. -->
	{#if jobDetail.isVideoDisc && $isAdmin}
		<MediaTypeSwitch {job} handSetCount={jobDetail.handSetCount} onchanged={onmediatypechanged} />
	{/if}
	{#if jobDetail.canApply && $isAdmin}
		<button type="button" data-testid="apply-open" onclick={onapply} class="btn job-detail-header-btn">
			Apply session
		</button>
	{/if}
	{#if $isAdmin}
		<JobActions {job} onaction={jobDetail.load} {ondelete} />
	{/if}
</div>

<style>
	/* the original header buttons were px-3 py-1.5 text-sm (0.75rem/0.375rem,
	   0.875rem) - between .btn's default and .btn-sm */
	.job-detail-header-btn {
		min-height: auto;
		padding: 0.375rem 0.75rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
	}
</style>
