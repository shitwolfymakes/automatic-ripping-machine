<script lang="ts">
	// The apply dialog's view of the output paths that stopped a session apply,
	// and whether Overwrite can get past them.
	import type { CollisionInfo } from '$lib/types/api.gen';

	interface Props {
		/** The output paths that stopped the apply. */
		collisions: CollisionInfo[];
		/** The applying job: collisions it owns get no owner suffix and are not cross-job. */
		jobId: string;
		/** True while an apply request is in flight. */
		submitting: boolean;
		/** Called when the user cancels. */
		onclose: () => void;
		/** Called when the user confirms Overwrite. */
		onoverwrite: () => void;
	}

	let { collisions, jobId, submitting, onclose, onoverwrite }: Props = $props();

	const hasDuplicateInRequest = $derived(collisions.some((c) => c.reason === 'duplicate_in_request'));

	// the backend refuses overwrite unconditionally when any collision is
	// owned by a DIFFERENT job (see _evict_colliding_tasks) — eviction
	// only ever removes tasks owned by the applying job. Offering Overwrite
	// here would loop the user into a 409 every time, so hide it and explain
	// instead. Same-job-only (or ownership-unknown) collisions keep the
	// normal Overwrite flow.
	const hasCrossJobCollision = $derived(
		collisions.some((c) => c.existing_job_id != null && c.existing_job_id !== jobId)
	);

	function collisionLabel(reason: CollisionInfo['reason']): string {
		if (reason === 'existing_task') return 'queued/done in DB';
		if (reason === 'on_disk') return 'exists on disk';
		return 'duplicate within this apply';
	}

	function collisionOwnerSuffix(c: CollisionInfo): string {
		if (!c.existing_job_id || c.existing_job_id === jobId) return '';
		return ` in job ${c.existing_job_id.slice(-8)}`;
	}
</script>

<p class="apply-session-collision-intro">This session can't be applied because of path collisions:</p>
<ul class="apply-session-collision-list">
	{#each collisions as c (c.output_path + c.reason)}
		<li>
			<code class="mono apply-session-collision-path">{c.output_path}</code>
			<span class="apply-session-recipe-faint">({collisionLabel(c.reason)}{collisionOwnerSuffix(c)})</span>
		</li>
	{/each}
</ul>

{#if hasCrossJobCollision}
	<p class="apply-session-collision-note" data-testid="cross-job-collision-notice">
		Some outputs are owned by another job. Cancel, or delete that job's output first.
	</p>
{:else if hasDuplicateInRequest}
	<p class="apply-session-collision-note">
		Two or more tracks resolve to the same output path - the session's template doesn't differentiate per track. Pick a
		session whose template includes <code>{'{track}'}</code>
		(e.g. <em>Movie -> Archive MKV</em>), or rip with a single-track preset.
		<strong>Overwrite</strong> won't help here.
	</p>
{:else}
	<p class="apply-session-collision-note">
		Confirm <strong>Overwrite</strong> to queue anyway. The transcoder writes to
		<code>.arm-inprogress</code> first, so partial writes never replace the existing file.
	</p>
{/if}

<div class="modal-actions">
	<button type="button" onclick={onclose} class="btn btn-ghost"> Cancel </button>
	{#if !hasCrossJobCollision && !hasDuplicateInRequest}
		<button
			type="button"
			data-testid="apply-session-overwrite"
			disabled={submitting}
			onclick={onoverwrite}
			class="btn btn-danger"
		>
			{submitting ? 'Applying...' : 'Overwrite'}
		</button>
	{/if}
</div>

<style>
	.apply-session-recipe-faint {
		color: var(--color-text-faint);
	}
	.apply-session-collision-intro {
		margin-top: 0.5rem;
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.apply-session-collision-list {
		margin-top: 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		font-size: 0.875rem;
	}
	.apply-session-collision-path {
		color: var(--color-text);
	}
	.apply-session-collision-note {
		margin-top: 0.75rem;
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
</style>
