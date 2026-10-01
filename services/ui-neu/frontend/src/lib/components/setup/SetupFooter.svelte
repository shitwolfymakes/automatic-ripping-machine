<script lang="ts">
	import Glyph from '$lib/components/Glyph.svelte';
	import type { StepMeta } from './steps';

	// The walkthrough's sticky action bar: Back, the save hint (or why Continue
	// is blocked), Skip for now on optional steps, and Continue.
	let {
		step,
		first,
		last,
		busy = false,
		canContinue = true,
		blockedReason = null,
		onback,
		onskip,
		oncontinue
	}: {
		step: StepMeta;
		first: boolean;
		last: boolean;
		busy?: boolean;
		canContinue?: boolean;
		blockedReason?: string | null;
		onback: () => void;
		onskip: () => void;
		oncontinue: () => void;
	} = $props();

	const hint = $derived(
		!canContinue && blockedReason
			? blockedReason
			: step.saveHint === 'live'
				? 'Changes on this step save as you make them.'
				: 'Saved when you press Continue.'
	);
</script>

<div class="setup-footer">
	<div class="setup-footer-grid">
		<div class="setup-footer-inner">
			{#if !first}
				<button type="button" class="btn" onclick={onback} disabled={busy}>
					<Glyph name="arrow-left" /> Back
				</button>
			{/if}
			<span class="setup-footer-hint" aria-live="polite">{hint}</span>
			<span class="setup-footer-actions">
				{#if step.optional}
					<button
						type="button"
						class="btn {step.id === 'notifications' ? '' : 'btn-link'} setup-footer-skip"
						onclick={onskip}
						disabled={busy}>Skip for now</button
					>
				{/if}
				<button
					type="button"
					class="btn btn-primary setup-footer-continue"
					onclick={oncontinue}
					disabled={busy || !canContinue}
				>
					{#if busy}Saving...{:else}{last ? 'Go to dashboard' : 'Continue'} <Glyph name="arrow-right" />{/if}
				</button>
			</span>
		</div>
	</div>
</div>

<style>
	.setup-footer {
		position: sticky;
		bottom: 0;
		z-index: 10;
		border-top: 1px solid var(--color-border);
		background: color-mix(in srgb, var(--color-page) 92%, transparent);
		backdrop-filter: blur(6px);
		padding: 0.75rem 1rem calc(0.75rem + env(safe-area-inset-bottom));
	}
	.setup-footer-inner {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem;
		max-width: 44rem;
		margin-left: auto;
		margin-right: auto;
	}
	.setup-footer-hint {
		flex: 1 1 12rem;
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
	.setup-footer-actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-left: auto;
	}
	.setup-footer-continue {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding-inline: 1.25rem;
	}
	/* desktop: line the actions up with the content column of SetupShell's grid */
	@media (min-width: 900px) {
		.setup-footer {
			padding-left: 1.5rem;
			padding-right: 1.5rem;
		}
		.setup-footer-grid {
			display: grid;
			grid-template-columns: 18rem minmax(0, 44rem);
			gap: 3rem;
			max-width: 69rem;
			margin: 0 auto;
		}
		.setup-footer-inner {
			grid-column: 2;
			max-width: none;
			margin: 0;
		}
	}
</style>
