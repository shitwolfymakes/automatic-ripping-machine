<script lang="ts">
	import FileRow from '$lib/components/files/FileRow.svelte';
	import SortIndicator from '$lib/components/shared/SortIndicator.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import type { FilesBrowser } from '$lib/stores/files-browser.svelte';

	interface Props {
		browser: FilesBrowser;
		onrename: (entryName: string, newName: string) => void;
		ondelete: (entryName: string, displayName: string) => void;
		onfixpermissions: (entryName: string, displayName: string) => void;
	}

	let { browser, onrename, ondelete, onfixpermissions }: Props = $props();
</script>

{#snippet sortIcon(key: string)}
	<SortIndicator dir={browser.sortIconDir(key)} />
{/snippet}

<table class="table">
	<thead>
		<tr>
			<th class="table-header w-10">
				{#if $isAdmin}
					<input
						type="checkbox"
						checked={browser.allSelected}
						onchange={browser.toggleSelectAll}
						class="files-page-select-all"
					/>
				{/if}
			</th>
			<th class="table-header">
				<button type="button" onclick={() => browser.toggleSort('name')} class="files-page-sort-btn">
					Name {@render sortIcon('name')}
				</button>
			</th>
			<th class="table-header files-page-cell-lg">Permissions</th>
			<th class="table-header table-right">
				<button type="button" onclick={() => browser.toggleSort('size')} class="files-page-sort-btn">
					Size {@render sortIcon('size')}
				</button>
			</th>
			<th class="table-header files-page-cell-md">
				<button type="button" onclick={() => browser.toggleSort('modified')} class="files-page-sort-btn">
					Modified {@render sortIcon('modified')}
				</button>
			</th>
			<th class="table-header table-right">Actions</th>
		</tr>
	</thead>
	<tbody>
		{#each browser.sortedEntries as entry (entry.name)}
			<FileRow
				{entry}
				currentPath={browser.current.subpath}
				selected={browser.selectedKeys.has(browser.selectionKey(entry.name))}
				readonly={browser.isReadonly}
				showActions={$isAdmin}
				onnavigate={() => browser.navigate(browser.current.root, browser.itemSubpath(entry.name))}
				onrename={(_, newName) => onrename(entry.name, newName)}
				ondelete={(_, name) => ondelete(entry.name, name)}
				ontoggle={() => browser.toggleSelect(entry.name)}
				onfixpermissions={(_, name) => onfixpermissions(entry.name, name)}
			/>
		{/each}
	</tbody>
</table>

<style>
	/* replaces the banned inline `hidden lg:table-cell`/`hidden
	   md:table-cell` (table/table-row/table-cell are Tailwind
	   display-utility names, banned outright by the lint per Task 11 fix
	   round 3 - only the table block's own classes may set that display
	   value) */
	.files-page-cell-lg {
		display: none;
	}
	@media (min-width: 1024px) {
		.files-page-cell-lg {
			display: table-cell;
		}
	}
	.files-page-cell-md {
		display: none;
	}
	@media (min-width: 768px) {
		.files-page-cell-md {
			display: table-cell;
		}
	}
	.files-page-select-all {
		height: 1rem;
		width: 1rem;
		border-radius: var(--radius-sm);
		border: 1px solid var(--color-border-strong);
		accent-color: var(--color-primary);
	}
	.files-page-sort-btn {
		color: inherit;
	}
	.files-page-sort-btn:hover {
		color: var(--color-text-secondary);
	}
</style>
