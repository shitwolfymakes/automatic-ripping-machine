<script lang="ts">
	import type { FileEntry } from '$lib/api/files';
	import { formatBytes, formatDateTime } from '$lib/utils/format';
	import FileIcon from './FileIcon.svelte';
	import Skeleton from './Skeleton.svelte';

	interface Props {
		entry?: FileEntry;
		currentPath?: string | null;
		selected?: boolean;
		readonly?: boolean;
		/** Selection + rename/delete/fix-permissions are write surfaces — hidden for guests. */
		showActions?: boolean;
		onnavigate?: (path: string) => void;
		onrename?: (path: string, name: string) => void;
		ondelete?: (path: string, name: string) => void;
		ontoggle?: (path: string) => void;
		onfixpermissions?: (path: string, name: string) => void;
	}

	let { entry, currentPath, selected = false, readonly: ro = false, showActions = true, onnavigate, onrename, ondelete, ontoggle, onfixpermissions }: Props = $props();

	let editing = $state(false);
	let editName = $state('');

	let fullPath = $derived((currentPath ?? '') + '/' + (entry?.name ?? ''));

	function startRename() {
		editName = entry?.name ?? '';
		editing = true;
	}

	function confirmRename() {
		if (editName && editName !== entry?.name) {
			onrename?.(fullPath, editName);
		}
		editing = false;
	}

	function cancelRename() {
		editing = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') confirmRename();
		if (e.key === 'Escape') cancelRename();
	}

	function handleClick() {
		if (entry?.type === 'directory') {
			onnavigate?.(fullPath);
		}
	}
</script>

{#if !entry}
	<tr aria-busy="true">
		{#each { length: 6 } as _}
			<td class="p-2"><Skeleton variant="line" width="80%" height="1rem" /></td>
		{/each}
	</tr>
{:else}
<tr class="table-row" data-selected={selected}>
	<!-- Checkbox -->
	<td class="table-cell w-10">
		{#if showActions}
			<input
				type="checkbox"
				checked={selected}
				onchange={() => ontoggle?.(fullPath)}
				class="file-row-checkbox"
			/>
		{/if}
	</td>

	<!-- Name -->
	<td class="table-cell">
		{#if editing}
			<div class="flex items-center gap-2">
				<FileIcon category={entry.category} />
				<input
					type="text"
					bind:value={editName}
					onkeydown={handleKeydown}
					class="field-control flex-1 file-row-edit-input"
				/>
				<button
					type="button"
					onclick={confirmRename}
					class="btn btn-icon file-row-confirm-btn"
					title="Confirm"
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
					</svg>
				</button>
				<button
					type="button"
					onclick={cancelRename}
					class="btn btn-icon"
					title="Cancel"
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
		{:else}
			<button
				type="button"
				onclick={handleClick}
				class="file-row-name-btn"
				data-clickable={entry.type === 'directory'}
			>
				<FileIcon category={entry.category} />
				<span class="file-row-name">{entry.name}</span>
			</button>
		{/if}
	</td>

	<!-- Permissions -->
	<td class="table-cell file-row-cell-lg">
		{#if entry.permissions}
			<code class="mono file-row-permissions">{entry.permissions}</code>
		{/if}
	</td>

	<!-- Size -->
	<td class="table-cell table-right file-row-muted">
		{entry.size ? formatBytes(entry.size) : '--'}
	</td>

	<!-- Modified -->
	<td class="table-cell file-row-muted file-row-cell-md">
		{formatDateTime(entry.modified)}
	</td>

	<!-- Actions -->
	<td class="table-cell table-right">
		{#if showActions}
			<div class="flex items-center justify-end gap-1">
				<!-- Fix permissions -->
				<button
					type="button"
					onclick={() => onfixpermissions?.(fullPath, entry.name)}
					disabled={ro}
					class="btn btn-icon file-row-action-btn file-row-action-btn-info"
					title={ro ? 'Read-only mount' : 'Fix permissions'}
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
					</svg>
				</button>
				<!-- Rename -->
				<button
					type="button"
					onclick={startRename}
					disabled={ro}
					class="btn btn-icon file-row-action-btn"
					title={ro ? 'Read-only mount' : 'Rename'}
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
					</svg>
				</button>
				<!-- Delete -->
				<button
					type="button"
					onclick={() => ondelete?.(fullPath, entry.name)}
					disabled={ro}
					class="btn btn-icon file-row-action-btn file-row-action-btn-danger"
					title={ro ? 'Read-only mount' : 'Delete'}
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
					</svg>
				</button>
			</div>
		{/if}
	</td>
</tr>
{/if}

<style>
	.file-row-checkbox { height: 1rem; width: 1rem; border-radius: var(--radius-sm); border: 1px solid var(--color-border-strong); accent-color: var(--color-primary); }
	.file-row-edit-input { width: auto; }
	/* the confirm/cancel icon buttons keep .btn-icon's box but need their
	   own tone (green/muted), not .btn-icon's default primary hover */
	.file-row-confirm-btn { color: var(--color-success); }
	.file-row-confirm-btn:hover { background: var(--color-success-soft); color: var(--color-success); }
	.file-row-name-btn { display: flex; align-items: center; gap: 0.5rem; cursor: default; }
	.file-row-name-btn[data-clickable="true"] { cursor: pointer; }
	.file-row-name-btn[data-clickable="true"]:hover .file-row-name { color: var(--color-primary); }
	.file-row-name { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text); }
	.file-row-permissions { color: var(--color-text-faint); }
	.file-row-muted { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.file-row-action-btn:disabled { opacity: 0.3; pointer-events: none; }
	.file-row-action-btn-info:hover { background: var(--color-info-soft); color: var(--color-info); }
	.file-row-action-btn-danger:hover { background: var(--color-danger-soft); color: var(--color-danger); }
	/* replaces the banned inline `hidden lg:table-cell` (table/table-row/
	   table-cell are Tailwind display-utility names, banned outright by
	   the lint per Task 11 fix round 3 - only the table block's own
	   classes may set that display value) */
	.file-row-cell-lg { display: none; }
	@media (min-width: 1024px) {
		.file-row-cell-lg { display: table-cell; }
	}
	/* replaces the banned inline `hidden md:table-cell` */
	.file-row-cell-md { display: none; }
	@media (min-width: 768px) {
		.file-row-cell-md { display: table-cell; }
	}
</style>
