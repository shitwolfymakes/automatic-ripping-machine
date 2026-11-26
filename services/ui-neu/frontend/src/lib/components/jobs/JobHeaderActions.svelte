<script lang="ts">
	import JobActions from '$lib/components/jobs/JobActions.svelte';
	import MediaTypeSwitch from '$lib/components/episodes/MediaTypeSwitch.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import type { JobDetail } from '$lib/stores/job-detail.svelte';
	import type { JobView } from '$lib/types/api.gen';
	import { isAwaitingIdentity } from '$lib/jobs/status-groups';

	// The two types the switch offers (a narrower set than the API's MediaType).
	type MediaType = 'movie' | 'tv';

	interface Props {
		job: JobView;
		jobDetail: JobDetail;
		onmediatypechanged: (type: MediaType) => void;
		onidentify: () => void;
		onapply: () => void;
		ondelete: () => void;
	}

	let { job, jobDetail, onmediatypechanged, onidentify, onapply, ondelete }: Props = $props();

	// Identify is "Edit identity" once an identity already exists (post-rip /
	// identified), otherwise "Identify disc" for the auto-id-failed case.
	let identifyLabel = $derived(isAwaitingIdentity(job.status) ? 'Identify disc' : 'Edit identity');
</script>

<div class="flex flex-wrap items-center gap-2 ml-auto">
	<!-- The type is part of the identity, so its switch sits beside Edit identity. -->
	{#if jobDetail.isVideoDisc && $isAdmin}
		<MediaTypeSwitch {job} handSetCount={jobDetail.handSetCount} onchanged={onmediatypechanged} />
	{/if}
	<!-- A video job with an identity edits it in place on the facts grid and
	     searches from the tab below; the dialog stays for a disc still waiting
	     for an identity, and for CDs (album, artist, track titles). -->
	{#if jobDetail.canResolve && $isAdmin && (jobDetail.isCdDisc || isAwaitingIdentity(job.status))}
		<button type="button" data-testid="identify-open" onclick={onidentify} class="btn job-detail-header-btn">
			{identifyLabel}
		</button>
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
	/* header buttons are text-sm (0.875rem) with 0.375rem/0.75rem padding - between .btn's default and .btn-sm */
	.job-detail-header-btn {
		min-height: auto;
		padding: 0.375rem 0.75rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
	}
</style>
