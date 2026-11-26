<script lang="ts">
	import { features } from '$lib/features';
	import { formatBytes } from '$lib/utils/format';
	import type { OrphanFolders } from '$lib/stores/orphan-folders.svelte';

	interface Props {
		orphans: OrphanFolders;
	}

	let { orphans }: Props = $props();
</script>

<!-- Orphan folders modal -->
{#if features.maintenance && orphans.isOpen}
	<div class="modal">
		<button
			type="button"
			class="modal-backdrop files-page-modal-backdrop"
			aria-label="Close dialog"
			onclick={() => (orphans.isOpen = false)}
		></button>
		<div class="modal-panel files-page-orphan-panel">
			<!-- Header -->
			<div class="shrink-0 files-page-modal-header">
				<h3 class="modal-title">Orphan Folders</h3>
				<p class="files-page-modal-subtitle">Folders not associated with any job</p>
			</div>

			<!-- Feedback -->
			{#if orphans.feedback}
				<div class="shrink-0 files-page-modal-feedback-row">
					<div
						class="alert files-page-orphan-feedback {orphans.feedback.type === 'success'
							? 'alert-success'
							: 'alert-danger'}"
					>
						{orphans.feedback.message}
					</div>
				</div>
			{/if}

			<!-- Content (scrollable) -->
			<div class="min-h-0 flex-1 overflow-y-auto">
				{#if orphans.loading}
					<div class="flex items-center justify-center p-8">
						<svg class="mr-2 h-5 w-5 spin files-page-spinner" viewBox="0 0 24 24">
							<circle class="spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
							<path class="spinner-fill" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
						</svg>
						<span class="files-page-loading-text">Loading...</span>
					</div>
				{:else if orphans.data && orphans.data.folders.length > 0}
					{#each orphans.data.folders as folder (folder.path)}
						<div class="list-row files-page-orphan-row">
							<input
								type="checkbox"
								checked={orphans.selected.has(folder.path)}
								onchange={() => orphans.toggle(folder.path)}
								disabled={orphans.busy}
								class="files-page-select-all"
							/>
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
							<div class="min-w-0 flex-1">
								<div class="truncate files-page-orphan-name">{folder.name}</div>
								<div class="files-page-orphan-size">{formatBytes(folder.size_bytes)}</div>
							</div>
							<span class="badge files-page-category-badge" data-category={folder.category}>
								{folder.category}
							</span>
							<button
								type="button"
								onclick={() => orphans.deleteOne(folder.path)}
								disabled={orphans.busy}
								class="btn btn-icon files-page-orphan-delete"
								title="Delete folder"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
									/>
								</svg>
							</button>
						</div>
					{/each}
				{:else if orphans.data}
					<div class="files-page-empty">No orphan folders found</div>
				{:else}
					<div class="files-page-empty files-page-empty-error">Failed to load orphan folders</div>
				{/if}
			</div>

			<!-- Footer -->
			<div class="shrink-0 files-page-modal-footer">
				<div class="flex items-center justify-between">
					<div>
						{#if orphans.selected.size > 0}
							<button
								type="button"
								onclick={orphans.deleteSelected}
								disabled={orphans.busy}
								class="btn files-page-bulk-btn files-page-bulk-btn-danger"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
									/>
								</svg>
								Delete {orphans.selected.size} selected
							</button>
						{/if}
					</div>
					<button type="button" onclick={() => (orphans.isOpen = false)} class="btn"> Close </button>
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	/* original was px-3 py-1.5 (0.75rem/0.375rem) */
	.files-page-orphan-feedback {
		padding: 0.375rem 0.75rem;
	}
	/* original bulk-action buttons were px-3 py-1.5 text-xs (0.75rem/1rem),
	   smaller than .btn's own default 1rem/0.5rem/text-sm - restated to
	   match; the icon+label gap (gap-1.5) is close enough to .btn's own
	   0.375rem default that no override is needed there */
	.files-page-bulk-btn {
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.files-page-bulk-btn-danger {
		border: 0;
		background: var(--color-danger);
		color: var(--color-on-primary);
	}
	/* darkens on hover like the original's bg-red-600 -> hover:bg-red-700;
	   no darker danger token exists, so filter substitutes for a literal
	   colour (the lint bans raw colour keywords, even inside color-mix) */
	.files-page-bulk-btn-danger:hover {
		filter: brightness(0.9);
	}
	.files-page-folder-icon {
		color: var(--color-warning);
	}
	.files-page-empty {
		padding: 2rem;
		text-align: center;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.files-page-select-all {
		height: 1rem;
		width: 1rem;
		border-radius: var(--radius-sm);
		border: 1px solid var(--color-border-strong);
		accent-color: var(--color-primary);
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
	.files-page-modal-feedback-row {
		border-bottom: 1px solid var(--color-border);
		padding: 0.5rem 1.5rem;
	}
	.files-page-spinner {
		color: var(--color-text-faint);
	}
	.files-page-loading-text {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	/* the original row was a plain flex row (no hover/pointer affordance -
	   only its checkbox/delete button are interactive); list-row's own
	   cursor:pointer/hover-tint are for a clickable row and don't apply here */
	.files-page-orphan-row {
		grid-template-columns: auto auto 1fr auto auto;
		gap: 0.75rem;
		padding: 0.625rem 1.5rem;
		cursor: default;
	}
	.files-page-orphan-row:hover {
		background: transparent;
	}
	.files-page-orphan-name {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-text);
	}
	.files-page-orphan-size {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	/* the original category pill used two literal hues with no shared
	   badge look (rounded-full px-2 py-0.5 text-xs font-medium); nearest
	   tones are warning (raw) and success (completed) */
	.files-page-category-badge {
		border-radius: 9999px;
	}
	.files-page-category-badge[data-category='raw'] {
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
	.files-page-category-badge[data-category='completed'] {
		background: var(--color-success-soft);
		color: var(--color-on-success-soft);
	}
	.files-page-orphan-delete {
		color: var(--color-danger);
	}
	.files-page-orphan-delete:hover {
		background: var(--color-danger-soft);
		color: var(--color-danger);
	}
	.files-page-modal-footer {
		border-top: 1px solid var(--color-border);
		padding: 1rem 1.5rem;
	}
</style>
