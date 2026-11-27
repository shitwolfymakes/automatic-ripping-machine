<script lang="ts">
	import LiveProgressLine from '$lib/components/jobs/LiveProgressLine.svelte';
	import { retryTrackStage } from '$lib/api/jobs';
	import { jobLive } from '$lib/stores/job-live.svelte';
	import { followsStageFeed, isStageActive, stageProgressSample, stageWords } from '$lib/jobs/staging';
	import { errorMessage } from '$lib/utils/errors';
	import { isAdmin } from '$lib/stores/auth';
	import type { TrackStageView } from '$lib/types/api.gen';

	interface Props {
		jobId: string;
		trackId: string;
		stage: TrackStageView;
		/** Called once a retry was accepted, so the page reloads the job. */
		onretried: () => void;
	}

	let { jobId, trackId, stage, onretried }: Props = $props();

	let retrying = $state(false);
	let retryError = $state<string | null>(null);

	$effect(() => {
		if (!followsStageFeed(stage)) return;
		return jobLive.followStage(trackId);
	});

	async function retry() {
		retrying = true;
		retryError = null;
		try {
			await retryTrackStage(jobId, trackId);
			onretried();
		} catch (e) {
			retryError = errorMessage(e, 'Could not retry');
		} finally {
			retrying = false;
		}
	}
</script>

<tr data-testid="track-stage-row">
	<td colspan="99" class="table-cell" data-label="">
		{#if isStageActive(stage)}
			<div class="stack-tight">
				<span class="track-stage-label">{stageWords(stage)}</span>
				<LiveProgressLine
					sample={stageProgressSample(stage, jobLive.stage(trackId))}
					waitingText="Waiting for the stager"
				/>
			</div>
		{:else}
			<div class="alert alert-danger" role="alert">
				<span class="track-stage-label">{stageWords(stage)}:</span>
				{stage.last_error ?? 'unknown error'}
				{#if $isAdmin}
					<button type="button" class="btn btn-sm" disabled={retrying} onclick={retry}>Retry</button>
				{/if}
				{#if retryError}<span class="field-error" role="alert">{retryError}</span>{/if}
			</div>
		{/if}
	</td>
</tr>

<style>
	.track-stage-label {
		font-weight: 600;
	}
</style>
