<script lang="ts">
	import type { SetupStep, SetupView } from '$lib/types/api.gen';
	import Glyph from '$lib/components/Glyph.svelte';
	import { STEPS, STATE_WORD, uiState, stepIndex, type StepUiState } from './steps';

	// Every step with its state as a glyph + word (never colour alone). Done,
	// skipped and needs-attention steps can be revisited; not-started ones
	// can't be jumped to. On narrow screens it collapses to a progress header.
	let {
		current,
		progress,
		onselect
	}: { current: SetupStep; progress: SetupView['progress']; onselect: (s: SetupStep) => void } = $props();

	let open = $state(false);
	const currentIndex = $derived(stepIndex(current));
	const currentLabel = $derived(STEPS[currentIndex]?.label ?? '');

	function select(id: SetupStep) {
		open = false;
		onselect(id);
	}
</script>

{#snippet marker(state: StepUiState, n: number)}
	<span class="setup-stepper-marker" data-state={state} aria-hidden="true">
		{#if state === 'done'}<Glyph name="check" class="h-3.5 w-3.5" />
		{:else if state === 'skipped'}<Glyph name="minus-circle" class="h-4 w-4" />
		{:else if state === 'attention'}<Glyph name="warning" class="h-3.5 w-3.5" />
		{:else}{n}{/if}
	</span>
{/snippet}

{#snippet list()}
	<ol class="setup-stepper-list">
		{#each STEPS as s, i (s.id)}
			{@const state = uiState(s.id, current, progress)}
			<li>
				<button
					type="button"
					class="setup-stepper-item"
					data-state={state}
					aria-current={state === 'current' ? 'step' : undefined}
					disabled={state === 'not-started'}
					onclick={() => select(s.id)}
				>
					{@render marker(state, i + 1)}
					<span class="setup-stepper-text">
						<span class="setup-stepper-label">{s.label}</span>
						<span class="setup-stepper-state">{STATE_WORD[state]}{s.optional ? ' · Optional' : ''}</span>
					</span>
				</button>
			</li>
		{/each}
	</ol>
{/snippet}

<nav class="setup-stepper" aria-label="Setup steps">
	<div class="setup-stepper-desktop">{@render list()}</div>
	<div class="setup-stepper-mobile">
		<button
			type="button"
			class="setup-stepper-toggle"
			aria-expanded={open}
			aria-controls="setup-stepper-mobile-list"
			onclick={() => (open = !open)}
		>
			<span>Step {currentIndex + 1} of {STEPS.length} · <strong>{currentLabel}</strong></span>
			<Glyph name={open ? 'chevron-up' : 'chevron-down'} />
		</button>
		<div class="setup-stepper-bar" aria-hidden="true">
			<span style="width: {((currentIndex + 1) / STEPS.length) * 100}%"></span>
		</div>
		{#if open}
			<div id="setup-stepper-mobile-list" class="setup-stepper-mobile-list">{@render list()}</div>
		{/if}
	</div>
</nav>

<style>
	.setup-stepper-list {
		display: grid;
		gap: 0.25rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.setup-stepper-item {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 0.75rem;
		border: 0;
		border-radius: var(--radius-lg);
		background: none;
		padding: 0.5rem 0.75rem;
		text-align: left;
		color: var(--color-text);
		cursor: pointer;
	}
	.setup-stepper-item:hover:not(:disabled) {
		background: var(--color-primary-tint-1);
	}
	.setup-stepper-item:disabled {
		cursor: default;
	}
	.setup-stepper-item[data-state='current'] {
		background: var(--color-primary-tint-2);
	}
	.setup-stepper-marker {
		flex: none;
		display: grid;
		place-items: center;
		width: 1.75rem;
		height: 1.75rem;
		border: 1.5px solid var(--color-border-strong);
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--color-text-muted);
	}
	.setup-stepper-marker[data-state='current'] {
		border-color: var(--color-primary);
		background: var(--color-primary);
		color: var(--color-on-primary);
	}
	.setup-stepper-marker[data-state='done'] {
		border-color: transparent;
		background: var(--color-success-soft);
		color: var(--color-on-success-soft);
	}
	.setup-stepper-marker[data-state='skipped'] {
		border-color: transparent;
		color: var(--color-text-muted);
	}
	.setup-stepper-marker[data-state='attention'] {
		border-color: transparent;
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
	.setup-stepper-text {
		display: grid;
		min-width: 0;
	}
	.setup-stepper-label {
		font-size: 0.9375rem;
		line-height: 1.3;
	}
	.setup-stepper-item[data-state='current'] .setup-stepper-label {
		font-weight: 600;
	}
	.setup-stepper-state {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
	.setup-stepper-item[data-state='current'] .setup-stepper-state {
		color: var(--color-primary-text);
	}
	.setup-stepper-item[data-state='attention'] .setup-stepper-state {
		color: var(--color-on-warning-soft);
	}
	.setup-stepper-mobile {
		display: none;
	}
	.setup-stepper-toggle {
		display: flex;
		width: 100%;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		border: 0;
		background: none;
		padding: 0.25rem 0;
		color: var(--color-text);
		font-size: 0.9375rem;
		cursor: pointer;
	}
	.setup-stepper-bar {
		margin-top: 0.5rem;
		height: 0.25rem;
		border-radius: 999px;
		background: var(--color-primary-tint-2);
		overflow: hidden;
	}
	.setup-stepper-bar span {
		display: block;
		height: 100%;
		background: var(--color-primary);
	}
	.setup-stepper-mobile-list {
		margin-top: 0.75rem;
	}
	@media (max-width: 899px) {
		.setup-stepper-desktop {
			display: none;
		}
		.setup-stepper-mobile {
			display: block;
		}
	}
</style>
