<script lang="ts">
	import { plural } from '$lib/utils/plural';
	import Glyph from '$lib/components/Glyph.svelte';
	import { childSubpath } from '$lib/files/files';
	import type { MovePicker } from '$lib/stores/move-picker.svelte';

	interface Props {
		picker: MovePicker;
		count: number;
		onconfirm: () => void;
	}

	let { picker, count, onconfirm }: Props = $props();
</script>

<!-- Bulk move dialog — browsable directory picker -->
{#if picker.isOpen}
	<div class="modal">
		<button
			type="button"
			class="modal-backdrop files-page-modal-backdrop"
			aria-label="Close dialog"
			onclick={picker.close}
		></button>
		<div class="modal-panel files-page-orphan-panel">
			<!-- Header -->
			<div class="shrink-0 files-page-modal-header">
				<h3 class="modal-title">
					Move {count}
					{plural(count, 'item')}
				</h3>
				<p class="files-page-modal-subtitle">Browse to the destination folder</p>
			</div>

			<!-- Current picker location -->
			<div class="shrink-0 files-page-picker-location">
				<div class="flex items-center gap-2 files-page-picker-location-text">
					<svg class="h-4 w-4 shrink-0 files-page-folder-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="1.5"
							d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
						/>
					</svg>
					<span class="files-page-picker-path">{picker.displayPath()}</span>
					{#if picker.atSource}
						<span class="badge files-page-current-badge">current</span>
					{/if}
				</div>
			</div>

			<!-- Folder list (scrollable) -->
			<div class="min-h-0 flex-1 overflow-y-auto">
				{#if picker.loading}
					<div class="flex items-center justify-center p-8">
						<svg class="mr-2 h-5 w-5 spin files-page-spinner" viewBox="0 0 24 24">
							<circle class="spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
							<path class="spinner-fill" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
						</svg>
					</div>
				{:else}
					<!-- Go up -->
					{#if picker.canGoUp}
						<button type="button" onclick={picker.goUp} class="flex w-full items-center gap-3 files-page-picker-row">
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 17l-5-5m0 0l5-5m-5 5h12" />
							</svg>
							..
						</button>
					{/if}

					{#if picker.folders.length === 0 && !picker.canGoUp}
						<div class="files-page-picker-empty">No subfolders</div>
					{/if}

					{#each picker.folders as folder (folder.name)}
						<button
							type="button"
							onclick={() => picker.load(picker.location.root, childSubpath(picker.location.subpath, folder.name))}
							class="flex w-full items-center gap-3 files-page-picker-row files-page-picker-row-folder"
						>
							<svg
								class="h-5 w-5 shrink-0 files-page-folder-icon"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="1.5"
									d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
								/>
							</svg>
							{folder.name}
							<Glyph name="chevron-right" class="ml-auto h-4 w-4 files-page-chevron" />
						</button>
					{/each}
				{/if}
			</div>

			<!-- Footer -->
			<div class="shrink-0 files-page-modal-footer">
				<div class="flex justify-end gap-3">
					<button type="button" onclick={picker.close} class="btn"> Cancel </button>
					<button
						type="button"
						onclick={onconfirm}
						disabled={picker.atSource}
						class="btn btn-primary"
						title={picker.atSource ? 'Navigate to a different folder first' : ''}
					>
						Move here
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	.files-page-picker-location {
		border-bottom: 1px solid var(--color-border);
		background: var(--color-page);
		padding: 0.5rem 1.5rem;
	}
	.files-page-picker-location-text {
		font-size: 0.875rem;
		line-height: 1.25rem;
	}
	.files-page-picker-path {
		font-weight: 500;
		color: var(--color-text);
	}
	/* original was a plain lowercase gray-200/gray-600 tag, not .badge's
	   primary-tinted pill nor .badge-sm's uppercase transform - no neutral
	   token exists (spec 5.1), so this keeps .badge's shape (pill, weight,
	   size) but restates the case and a text-sm-scale padding */
	.files-page-current-badge {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		text-transform: none;
		letter-spacing: normal;
	}
	.files-page-picker-row {
		border-bottom: 1px solid var(--color-border);
		padding: 0.625rem 1.5rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-secondary);
	}
	.files-page-picker-row:hover {
		background: var(--color-primary-tint-1);
	}
	.files-page-picker-row-folder {
		color: var(--color-text);
	}
	.files-page-picker-empty {
		padding: 1.5rem;
		text-align: center;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	/* :global: forwarded through Glyph's class prop */
	:global(.files-page-chevron) {
		color: var(--color-text-faint);
	}
	.files-page-modal-backdrop {
		position: absolute;
		inset: 0;
	}
	.files-page-orphan-panel {
		display: flex;
		width: 100%;
		max-width: 32rem;
		max-height: 80vh;
		flex-direction: column;
		padding: 0;
	}
	.files-page-modal-header {
		border-bottom: 1px solid var(--color-border);
		padding: 1rem 1.5rem;
	}
	.files-page-modal-subtitle {
		margin-top: 0.25rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.files-page-spinner {
		color: var(--color-text-faint);
	}
	.files-page-modal-footer {
		border-top: 1px solid var(--color-border);
		padding: 1rem 1.5rem;
	}
	.files-page-folder-icon {
		color: var(--color-warning);
	}
</style>
