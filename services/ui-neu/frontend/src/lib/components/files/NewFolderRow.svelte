<script lang="ts">
	import Glyph from '$lib/components/shared/Glyph.svelte';

	interface Props {
		name: string;
		onconfirm: () => void;
		oncancel: () => void;
	}

	let { name = $bindable(), onconfirm, oncancel }: Props = $props();

	function handleNewFolderKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') onconfirm();
		if (e.key === 'Escape') oncancel();
	}
</script>

<div class="flex items-center gap-2 files-page-nav-row files-page-new-folder-row">
	<span class="w-10"></span>
	<Glyph name="folder-plus" class="h-5 w-5 shrink-0 files-page-folder-icon" />
	<input
		type="text"
		bind:value={name}
		onkeydown={handleNewFolderKeydown}
		placeholder="Folder name"
		class="field-control flex-1 files-page-new-folder-input"
	/>
	<button type="button" onclick={onconfirm} class="btn btn-icon files-page-new-folder-confirm" title="Create">
		<Glyph name="check" />
	</button>
	<button type="button" onclick={oncancel} class="btn btn-icon" title="Cancel">
		<Glyph name="x" />
	</button>
</div>

<style>
	.files-page-nav-row {
		border-bottom: 1px solid var(--color-border);
		padding: 0.5rem 0.75rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-secondary);
	}
	.files-page-nav-row:hover {
		background: var(--color-primary-tint-1);
	}
	.files-page-new-folder-row {
		background: var(--color-primary-tint-1);
	}
	.files-page-new-folder-input {
		width: auto;
		min-height: auto;
		padding: 0.25rem 0.5rem;
	}
	/* :global: set on Glyph through its class prop */
	:global(.files-page-folder-icon) {
		color: var(--color-warning);
	}
	.files-page-new-folder-confirm {
		color: var(--color-success);
	}
	.files-page-new-folder-confirm:hover {
		background: var(--color-success-soft);
		color: var(--color-success);
	}
</style>
