<script lang="ts">
	// The ISO picker's footer: a helper line and the Close, or Cancel and
	// Start rip, buttons.
	interface Props {
		/** True while the ISO library is not set up; the footer only offers Close. */
		notConfigured: boolean;
		/** True when picking a disc folder rather than an ISO file. */
		isFolderMode: boolean;
		/** Name of the picked ISO or folder, or null when nothing is picked. */
		selectedName: string | null;
		/** Path of the picked ISO or folder; Start stays disabled without one. */
		selectedPath: string | null;
		/** True while the rip is being started; disables Cancel and Start. */
		starting: boolean;
		/** Called when Close or Cancel is clicked. */
		onclose: () => void;
		/** Called when Start rip is clicked. */
		onstart: () => void;
	}

	let { notConfigured, isFolderMode, selectedName, selectedPath, starting, onclose, onstart }: Props = $props();
</script>

<div class="iso-picker-footer">
	{#if notConfigured}
		<p class="iso-picker-footer-helper">Nothing to pick until the library is set up.</p>
		<div class="flex gap-2">
			<button type="button" class="btn" onclick={() => onclose()}>Close</button>
		</div>
	{:else}
		<p class="iso-picker-footer-helper">
			{selectedName
				? `Selected: ${selectedName}`
				: isFolderMode
					? 'Pick a disc folder to start.'
					: 'Pick an ISO to start.'}
		</p>
		<div class="flex gap-2">
			<button type="button" class="btn" onclick={() => onclose()} disabled={starting}>Cancel</button>
			<button type="button" class="btn btn-primary" onclick={onstart} disabled={!selectedPath || starting}>
				{starting ? 'Starting...' : 'Start rip'}
			</button>
		</div>
	{/if}
</div>

<style>
	/* The slide-over's body (SlideOver.svelte's own markup) is the scrolling
	   container; pinning the footer to ITS bottom (rather than letting it
	   scroll away with the content) is this component's one deliberate
	   departure from the New-session slide-over pattern (spec 7.1). Negative
	   margins cancel that body's p-6 so the footer spans full-bleed. */
	.iso-picker-footer {
		position: sticky;
		bottom: -1.5rem;
		margin: 0 -1.5rem -1.5rem;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		border-top: 1px solid var(--color-border);
		background: var(--color-surface);
		padding: 0.75rem 1.5rem;
	}
	.iso-picker-footer-helper {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	@media (max-width: 400px) {
		.iso-picker-footer {
			flex-direction: column;
			align-items: stretch;
		}
	}
</style>
