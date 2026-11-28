<script lang="ts">
	import JobActions from '$lib/components/jobs/JobActions.svelte';
	import MediaTypeSwitch from '$lib/components/episodes/MediaTypeSwitch.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import type { JobDetail } from '$lib/stores/job-detail.svelte';
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
		<button type="button" data-testid="apply-open" onclick={onapply} class="btn btn-sm btn-primary">
			Apply session
		</button>
	{/if}
	{#if $isAdmin}
		<JobActions {job} onaction={jobDetail.load} {ondelete} />
	{/if}
</div>
