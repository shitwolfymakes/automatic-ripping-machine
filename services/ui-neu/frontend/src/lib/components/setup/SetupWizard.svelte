<script lang="ts">
	import type { SetupStatus } from '$lib/api/setup';
	import type { Component } from 'svelte';
	import { goto } from '$app/navigation';
	import { completeSetup } from '$lib/api/setup';
	import StepIndicator from './StepIndicator.svelte';
	import WelcomeStep from './WelcomeStep.svelte';
	import DriveScanStep from './DriveScanStep.svelte';
	import ReadinessCheckStep from './ReadinessCheckStep.svelte';
	import SettingsReviewStep from './SettingsReviewStep.svelte';

	interface SetupStep {
		id: string;
		label: string;
		component: Component<any>;
	}

	interface Props {
		status: SetupStatus;
	}

	let { status }: Props = $props();

	const steps: SetupStep[] = [
		{ id: 'welcome', label: 'Welcome', component: WelcomeStep },
		{ id: 'drives', label: 'Drives', component: DriveScanStep },
		{ id: 'readiness', label: 'Readiness', component: ReadinessCheckStep },
		{ id: 'settings', label: 'Settings', component: SettingsReviewStep },
	];

	let currentIndex = $state(0);
	let finishing = $state(false);

	let currentStep = $derived(steps[currentIndex]);
	let isFirst = $derived(currentIndex === 0);
	let isLast = $derived(currentIndex === steps.length - 1);

	function next() {
		if (currentIndex < steps.length - 1) currentIndex++;
	}

	function prev() {
		if (currentIndex > 0) currentIndex--;
	}

	async function finish() {
		finishing = true;
		try {
			await completeSetup();
			goto('/');
		} catch {
			finishing = false;
		}
	}
</script>

<div class="stack setup-wizard">
	<!-- Logo -->
	<div class="setup-wizard-logo">
		<img src="/img/arm-logo-black.png" alt="ARM" class="setup-wizard-logo-img setup-wizard-logo-light" />
		<img src="/img/arm-logo-white.png" alt="ARM" class="setup-wizard-logo-img setup-wizard-logo-dark" />
	</div>

	<!-- Progress -->
	<StepIndicator steps={steps.map(s => ({ id: s.id, label: s.label }))} {currentIndex} />

	<!-- Step content -->
	<div class="panel setup-wizard-panel">
		{#if currentStep.id === 'welcome'}
			<WelcomeStep {status} />
		{:else if currentStep.id === 'drives'}
			<DriveScanStep />
		{:else if currentStep.id === 'readiness'}
			<ReadinessCheckStep />
		{:else if currentStep.id === 'settings'}
			<SettingsReviewStep />
		{/if}
	</div>

	<!-- Navigation -->
	<div class="flex items-center justify-between">
		<button
			type="button"
			onclick={prev}
			disabled={isFirst}
			class="btn setup-wizard-back-btn"
		>
			Back
		</button>

		{#if isLast}
			<button
				type="button"
				onclick={finish}
				disabled={finishing}
				class="btn btn-primary setup-wizard-primary-btn"
			>
				{finishing ? 'Finishing...' : 'Finish Setup'}
			</button>
		{:else}
			<button
				type="button"
				onclick={next}
				class="btn btn-primary setup-wizard-primary-btn"
			>
				Next
			</button>
		{/if}
	</div>
</div>

<style>
	.setup-wizard { max-width: 42rem; margin: 0 auto; gap: 2rem; padding: 2rem 1rem; }
	.setup-wizard-logo { text-align: center; }
	.setup-wizard-logo-img { margin: 0 auto; height: 5rem; width: 5rem; }
	.setup-wizard-logo-dark { display: none; }
	/* The ARM wordmark is two pre-rendered bitmaps; dark mode swaps which
	   one is visible - same precedent as +layout.svelte's header logo. */
	/* :global: dark-mode logo swap, see the comment above */
	:global(.dark) .setup-wizard-logo-light { display: none; }
	/* :global: dark-mode logo swap, see the comment above */
	:global(.dark) .setup-wizard-logo-dark { display: block; }
	.setup-wizard-panel { border-radius: var(--radius-xl); }
	/* original was a ring (box-shadow), not .btn's real border - border: 0
	   plus the ring restated keeps the button's box height identical */
	.setup-wizard-back-btn { border: 0; box-shadow: 0 0 0 1px var(--color-border-strong); color: var(--color-text-secondary); }
	.setup-wizard-back-btn:hover { background: var(--color-primary-tint-1); }
	.setup-wizard-back-btn:disabled { opacity: 0; }
	/* original padding was px-6 py-2 (1.5rem/0.5rem), wider than .btn-primary's
	   default 1rem/0.5rem */
	.setup-wizard-primary-btn { padding: 0.5rem 1.5rem; }
</style>
