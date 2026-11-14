<script lang="ts">
	import type { DriveView } from '$lib/types/api.gen';
	import { DriveLifecycleActions } from '$lib/stores/drive-lifecycle-actions.svelte';
	import Glyph from '$lib/components/shared/Glyph.svelte';
	import DriveLifecycleRow from '$lib/components/drives/drive-lifecycle/DriveLifecycleRow.svelte';

	// Detected + ignored drives, shared by Settings > Drives and the setup
	// walkthrough's Drives step. Enrolling starts a ripper container, which
	// takes seconds and can fail per drive, so each row
	// carries its own progress and error state.
	interface Props {
		detected: DriveView[];
		ignored: DriveView[];
		onchanged: () => void;
		/** Set when enrolling can't work right now (e.g. the ripper service is down). */
		enrollDisabledReason?: string | null;
	}
	let { detected, ignored, onchanged, enrollDisabledReason = null }: Props = $props();

	let ignoredOpen = $state(false);
	const actions = new DriveLifecycleActions(() => onchanged());
	// Ids present at first render; anything detected later is flagged New.
	let firstSeen = $state<Set<string> | null>(null);

	$effect(() => {
		if (firstSeen === null) firstSeen = new Set(detected.map((d) => d.id));
	});

	const isNew = (d: DriveView) => firstSeen !== null && !firstSeen.has(d.id);
</script>

<div class="panel panel-compact stack drive-lifecycle-lists-panel" data-testid="drive-lifecycle-panel">
	<h3 class="drive-lifecycle-lists-title">Detected</h3>
	{#if enrollDisabledReason && detected.length > 0}
		<p class="alert alert-warning" data-testid="enroll-disabled-reason">{enrollDisabledReason}</p>
	{/if}
	{#if detected.length === 0}
		<p data-testid="detected-empty" class="drive-lifecycle-lists-empty">
			No unenrolled drives. Plug one in and it appears here on the next scan.
		</p>
	{:else}
		<div class="stack-sm stack">
			{#each detected as d (d.id)}
				<DriveLifecycleRow
					drive={d}
					ignored={false}
					isNew={isNew(d)}
					busy={actions.busy[d.id]}
					error={actions.errors[d.id]}
					{enrollDisabledReason}
					onenroll={() => actions.enroll(d.id)}
					ontoggleignore={() => actions.ignore(d.id)}
				/>
			{/each}
		</div>
	{/if}

	{#if ignored.length > 0}
		<button
			data-testid="ignored-toggle"
			aria-expanded={ignoredOpen}
			onclick={() => {
				ignoredOpen = !ignoredOpen;
			}}
			class="btn btn-link btn-sm drive-lifecycle-lists-ignored-toggle"
		>
			Ignored ({ignored.length})
			<Glyph name={ignoredOpen ? 'chevron-down' : 'chevron-right'} class="h-3.5 w-3.5" />
		</button>
		{#if ignoredOpen}
			<div class="stack-sm stack">
				{#each ignored as d (d.id)}
					<DriveLifecycleRow
						drive={d}
						ignored={true}
						isNew={false}
						busy={actions.busy[d.id]}
						error={actions.errors[d.id]}
						{enrollDisabledReason}
						onenroll={() => actions.enroll(d.id)}
						ontoggleignore={() => actions.unignore(d.id)}
					/>
				{/each}
			</div>
		{/if}
	{/if}
</div>

<style>
	.drive-lifecycle-lists-panel {
		gap: 0.75rem;
	}
	.drive-lifecycle-lists-title {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.drive-lifecycle-lists-empty {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-faint);
	}
	/* :global: .dark is the app-level scheme class on <html>, outside this component's own template */
	:global(.dark) .drive-lifecycle-lists-empty {
		color: var(--color-text-muted);
	}
	.drive-lifecycle-lists-ignored-toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-text-secondary);
	}
	.drive-lifecycle-lists-ignored-toggle:hover {
		text-decoration: underline;
	}
</style>
