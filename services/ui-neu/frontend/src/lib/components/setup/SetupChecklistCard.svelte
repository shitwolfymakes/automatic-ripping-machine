<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { SetupView } from '$lib/types/api.gen';
	import { fetchSetup, dismissSetupChecklist } from '$lib/api/setup';
	import { isAdmin } from '$lib/stores/auth';
	import { clearFinishLater } from '$lib/stores/setup.svelte';
	import Glyph from '$lib/components/Glyph.svelte';
	import CloseButton from '$lib/components/CloseButton.svelte';
	import { STEPS } from './steps';

	// Dashboard card listing whatever setup left open: steps skipped or needing
	// attention, or the whole walkthrough after "Finish later". Dismissal is
	// stored on the server (setup spec D3).
	let view = $state<SetupView | null>(null);
	let hidden = $state(false);

	const steps = STEPS.filter((s) => s.id !== 'finish');
	const stateOf = (id: string) => view?.progress[id]?.state ?? null;
	const open = $derived(steps.filter((s) => ['skipped', 'attention'].includes(stateOf(s.id) ?? '')));
	const done = $derived(steps.filter((s) => stateOf(s.id) === 'done').length);
	const incomplete = $derived(view !== null && view.completed_at === null);
	const visible = $derived(!hidden && view !== null && !view.checklist_dismissed && (incomplete || open.length > 0));

	onMount(async () => {
		if (!$isAdmin) return;
		try {
			view = await fetchSetup();
		} catch {
			view = null;
		}
	});

	async function dismiss() {
		hidden = true;
		try {
			view = await dismissSetupChecklist();
		} catch {
			/* hidden for now; it comes back on reload if the server didn't record it */
		}
	}

	function resume() {
		clearFinishLater();
		goto('/setup');
	}
</script>

{#if visible && view}
	<section class="panel setup-checklist" data-testid="setup-checklist" aria-labelledby="setup-checklist-title">
		<div class="setup-checklist-head">
			<div>
				<h2 id="setup-checklist-title" class="setup-checklist-title">
					Finish setting up ARM <span class="badge badge-sm badge-info">{done} of {steps.length} done</span>
				</h2>
				<p class="setup-checklist-help">ARM works without these. Finish them when you have a minute.</p>
			</div>
			<CloseButton onclick={dismiss} label="Dismiss setup checklist" />
		</div>
		<div class="setup-checklist-bar" aria-hidden="true">
			{#each steps as s (s.id)}
				<span data-state={stateOf(s.id) ?? 'pending'}></span>
			{/each}
		</div>
		<ul class="setup-checklist-rows">
			{#each open as s (s.id)}
				{@const st = stateOf(s.id)}
				<li class="setup-checklist-row" data-testid="setup-checklist-row-{s.id}">
					<span class="chip chip-sm {st === 'attention' ? 'chip-warning' : ''}">
						<Glyph name={st === 'attention' ? 'warning' : 'minus-circle'} class="h-3 w-3" />
						{st === 'attention' ? 'Needs attention' : 'Skipped'}
					</span>
					<span class="setup-checklist-label">{s.label}</span>
					<a class="btn btn-sm" href="/setup/{s.id}"
						>{st === 'attention' ? 'Fix' : 'Set up'} <Glyph name="arrow-right" /></a
					>
				</li>
			{/each}
		</ul>
		<div class="setup-checklist-foot">
			{#if incomplete}
				<button type="button" class="btn btn-primary" onclick={resume}>Resume setup</button>
			{/if}
			<span class="setup-checklist-help">Also in <a href="/settings#system">Settings, System</a></span>
		</div>
	</section>
{/if}

<style>
	.setup-checklist {
		display: grid;
		gap: 0.875rem;
		padding: 1.25rem;
	}
	/* Beside the page title on wide screens; on a phone the header row wraps
	   and the card takes the full width instead of a 200px column. */
	@media (max-width: 639px) {
		.setup-checklist {
			flex-basis: 100%;
		}
	}
	.setup-checklist-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.75rem;
	}
	.setup-checklist-title {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		font-size: 1.0625rem;
		font-weight: 600;
	}
	.setup-checklist-help {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.setup-checklist-bar {
		display: grid;
		grid-template-columns: repeat(8, 1fr);
		gap: 0.25rem;
	}
	.setup-checklist-bar span {
		height: 0.3125rem;
		border-radius: 999px;
		background: var(--color-primary-tint-3);
	}
	.setup-checklist-bar span[data-state='done'] {
		background: var(--color-success);
	}
	.setup-checklist-bar span[data-state='attention'] {
		background: var(--color-warning);
	}
	.setup-checklist-rows {
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.setup-checklist-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.75rem;
		border-top: 1px solid var(--color-border);
		padding: 0.625rem 0;
	}
	.setup-checklist-label {
		flex: 1 1 10rem;
		font-weight: 600;
	}
	.setup-checklist-foot {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem;
	}
</style>
