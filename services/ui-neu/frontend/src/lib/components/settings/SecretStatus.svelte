<script lang="ts">
	// A secret field's status under its input: saved, with a Remove
	// button, or to be removed on the next save.
	import Glyph from '$lib/components/shared/Glyph.svelte';

	interface Props {
		/** The field holds a saved secret. */
		saved: boolean;
		/** The operator removed the saved secret; it is cleared on save. */
		removed: boolean;
		/** Removes the saved secret. */
		onremove: () => void;
	}
	let { saved, removed, onremove }: Props = $props();
</script>

{#if saved}
	<div class="secret-status">
		<span class="chip chip-sm chip-success"><Glyph name="check" class="h-3 w-3" /> Saved</span>
		<span class="secret-status-note">Type a new key to replace it.</span>
		<button type="button" class="btn btn-link btn-sm" onclick={onremove}>Remove</button>
	</div>
{:else if removed}
	<div class="secret-status">
		<span class="chip chip-sm chip-warning"><Glyph name="minus-circle" class="h-3 w-3" /> Will be removed</span>
		<span class="secret-status-note">The key is cleared when you save.</span>
	</div>
{/if}

<style>
	.secret-status {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.25rem 0.5rem;
		font-size: 0.8125rem;
	}
	.secret-status-note {
		color: var(--color-text-muted);
	}
</style>
