<script lang="ts">
	// The add-channel form's footer: whether the channel is ready to
	// save, and the Cancel, Send test and Save buttons.
	import Glyph from '$lib/components/shared/Glyph.svelte';

	interface Props {
		/** Every required field is filled in. */
		ready: boolean;
		/** The required fields still missing, as the ready line names them. */
		missing: string[];
		variant: 'full' | 'compact';
		/** The channel's type can send a test (a bash script tests in its own panel). */
		testable: boolean;
		oncancel?: () => void;
		ontest: () => void;
		onsave: () => void;
	}
	let { ready, missing, variant, testable, oncancel, ontest, onsave }: Props = $props();
</script>

<div class="add-channel-form-footer">
	<span class="add-channel-form-ready" data-ready={ready}>
		{#if ready}<Glyph name="check" class="h-3.5 w-3.5" /> Ready to save{:else}Needs: {missing.join(', ')}{/if}
	</span>
	<div class="cluster">
		{#if variant === 'full'}
			<button type="button" onclick={() => oncancel?.()} class="btn btn-ghost">Cancel</button>
		{/if}
		{#if testable}
			<button type="button" onclick={() => ontest()} disabled={variant === 'compact' && !ready} class="btn"
				>Send test</button
			>
		{/if}
		{#if variant === 'full'}
			<button type="button" disabled={!ready} onclick={() => onsave()} class="btn btn-primary">Save channel</button>
		{/if}
	</div>
</div>

<style>
	.add-channel-form-footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.875rem 1.25rem;
		border-top: 1px solid var(--color-border);
	}
	.add-channel-form-ready {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	.add-channel-form-ready[data-ready='true'] {
		color: var(--color-status-success);
	}
</style>
