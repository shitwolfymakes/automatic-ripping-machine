<script lang="ts">
	import { onMount, tick, type Component } from 'svelte';
	import { goto } from '$app/navigation';
	import type { SetupStep, SetupView } from '$lib/types/api.gen';
	import SetupShell from '$lib/components/setup/SetupShell.svelte';
	import SetupStepper from '$lib/components/setup/SetupStepper.svelte';
	import SetupFooter from '$lib/components/setup/SetupFooter.svelte';
	import { STEPS, nextStep, prevStep, stepIndex, stepMeta, type SetupStepComponent } from '$lib/components/setup/steps';
	import AccountStep from '$lib/components/setup/steps/AccountStep.svelte';
	import SystemStep from '$lib/components/setup/steps/SystemStep.svelte';
	import DrivesStep from '$lib/components/setup/steps/DrivesStep.svelte';
	import MakemkvStep from '$lib/components/setup/steps/MakemkvStep.svelte';
	import MetadataStep from '$lib/components/setup/steps/MetadataStep.svelte';
	import DiscsStep from '$lib/components/setup/steps/DiscsStep.svelte';
	import TranscodingStep from '$lib/components/setup/steps/TranscodingStep.svelte';
	import NotificationsStep from '$lib/components/setup/steps/NotificationsStep.svelte';
	import FinishStep from '$lib/components/setup/steps/FinishStep.svelte';
	import { completeSetup } from '$lib/api/setup';
	import { setupState, loadSetup, markStep, clearFinishLater } from '$lib/stores/setup.svelte';

	let { data }: { data: { step: SetupStep } } = $props();

	type StepProps = { view: SetupView; setBlocked?: (reason: string | null) => void };
	type StepComponentType = Component<StepProps, SetupStepComponent>;
	const STEP_COMPONENTS: Record<SetupStep, StepComponentType> = {
		account: AccountStep,
		system: SystemStep,
		drives: DrivesStep,
		makemkv: MakemkvStep,
		metadata: MetadataStep,
		discs: DiscsStep,
		transcoding: TranscodingStep,
		notifications: NotificationsStep,
		finish: FinishStep
	};

	const meta = $derived(stepMeta(data.step)!);
	const index = $derived(stepIndex(data.step));
	const StepComponent = $derived(STEP_COMPONENTS[data.step]);

	let stepRef = $state<SetupStepComponent | undefined>();
	let busy = $state(false);
	let blockedReason = $state<string | null>(null);
	let error = $state<string | null>(null);
	let heading: HTMLHeadingElement | undefined = $state();

	onMount(async () => {
		try {
			const view = await loadSetup();
			// The password must change before anything else can load.
			if (view.admin_default_password && data.step !== 'account') goto('/setup/account', { replaceState: true });
		} catch {
			error = 'Could not load setup. Check that ARM is running, then reload.';
		}
	});

	// New step: clear the previous step's state and move focus to its heading.
	$effect(() => {
		void data.step;
		blockedReason = null;
		error = null;
		void tick().then(() => heading?.focus());
	});

	function go(step: SetupStep | null) {
		if (step) goto(`/setup/${step}`);
	}

	async function onContinue() {
		if (!stepRef || busy) return;
		busy = true;
		error = null;
		try {
			const result = await stepRef.commit();
			if (result === false) return;
			if (data.step === 'finish') {
				await completeSetup();
				clearFinishLater();
				goto('/');
				return;
			}
			await markStep(data.step, result === 'skip' ? 'skipped' : result);
			go(nextStep(data.step));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Saving this step failed';
		} finally {
			busy = false;
		}
	}

	async function onSkip() {
		if (busy) return;
		busy = true;
		try {
			await markStep(data.step, 'skipped');
			go(nextStep(data.step));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Skipping this step failed';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head>
	<title>ARM - Set up: {meta.label}</title>
</svelte:head>

<SetupShell showFinishLater={data.step !== 'account'}>
	{#snippet stepper()}
		<SetupStepper current={data.step} progress={setupState.view?.progress ?? {}} onselect={(s) => go(s)} />
	{/snippet}

	<div class="setup-step-page stack stack-lg">
		<header class="setup-step-header">
			<p class="setup-step-eyebrow">
				Step {index + 1} of {STEPS.length}
				{#if meta.optional}<span class="badge badge-sm">Optional</span>{/if}
			</p>
			<h1 id="setup-step-heading" tabindex="-1" bind:this={heading} class="setup-step-title">{meta.title}</h1>
			<p class="setup-step-intro">{meta.intro}</p>
		</header>

		{#if error}
			<div class="alert alert-danger" role="alert">{error}</div>
		{/if}

		{#if setupState.view}
			{#key data.step}
				<StepComponent
					bind:this={stepRef}
					view={setupState.view}
					setBlocked={(r: string | null) => (blockedReason = r)}
				/>
			{/key}
		{:else if !error}
			<p class="setup-step-loading">Loading...</p>
		{/if}
	</div>

	{#snippet footer()}
		<SetupFooter
			step={meta}
			first={index === 0}
			last={data.step === 'finish'}
			{busy}
			canContinue={!blockedReason && !!setupState.view}
			{blockedReason}
			onback={() => go(prevStep(data.step))}
			onskip={onSkip}
			oncontinue={onContinue}
		/>
	{/snippet}
</SetupShell>

<style>
	.setup-step-eyebrow {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.8125rem;
		font-weight: 700;
		color: var(--color-text-muted);
	}
	.setup-step-title {
		margin-top: 0.25rem;
		font-size: 2rem;
		line-height: 1.15;
		font-weight: 700;
		color: var(--color-text);
	}
	.setup-step-title:focus {
		outline: none;
	}
	.setup-step-title:focus-visible {
		outline: 2px solid var(--color-primary);
		outline-offset: 4px;
	}
	.setup-step-intro {
		margin-top: 0.5rem;
		color: var(--color-text-muted);
	}
	.setup-step-loading {
		color: var(--color-text-muted);
	}
	@media (max-width: 639px) {
		.setup-step-title {
			font-size: 1.625rem;
		}
	}
</style>
