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
	<svg class="h-5 w-5 shrink-0 files-page-folder-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			stroke-width="1.5"
			d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"
		/>
	</svg>
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
	.files-page-folder-icon {
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
