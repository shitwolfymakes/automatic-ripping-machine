<script lang="ts">
	interface Props {
		heldTasks: number;
	}

	let { heldTasks }: Props = $props();
</script>

<div class="stack stack-lg">
	<h1 class="page-title">Transcoder</h1>
	{#if heldTasks > 0}
		<div class="alert alert-warning" role="status" data-testid="transcoder-held-encode-tasks">
			{heldTasks === 1 ? '1 encode task is' : `${heldTasks} encode tasks are`} held. Re-run setup without --ripper-only to
			resume them.
		</div>
	{/if}
	<div class="panel transcoder-page-unavailable" data-testid="transcoder-unavailable">
		<p class="transcoder-page-unavailable-text">
			Transcoding is not available on this deployment (ripper-only install).
		</p>
	</div>
</div>

<style>
	/* Full-page ripper-only empty state - same centered-muted-text idiom as
	   .transcoder-page-empty / the dashboard's "No jobs found.", inside a
	   .panel since it stands alone rather than sitting under a section title. */
	.transcoder-page-unavailable {
		padding: 2rem;
		text-align: center;
	}
	.transcoder-page-unavailable-text {
		color: var(--color-text-faint);
	}
</style>
