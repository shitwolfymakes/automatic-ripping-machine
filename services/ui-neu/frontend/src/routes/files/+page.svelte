<script lang="ts">
	import { plural } from '$lib/utils/plural';
	import { errorMessage } from '$lib/utils/errors';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { renameFile, moveFile, deleteFile, createDirectory, fixPermissions } from '$lib/api/files';
	import { FilesBrowser } from '$lib/stores/filesBrowser.svelte';
	import { MovePicker } from '$lib/stores/movePicker.svelte';
	import { OrphanFolders } from '$lib/stores/orphanFolders.svelte';
	import type { BulkFeedback } from '$lib/utils/bulk-delete-feedback';
	import {
		parseSelectionKey,
		orderForDelete,
		bulkResultFeedback,
		cleanupFeedback,
		fixedPermissionsMessage
	} from '$lib/utils/files';
	import { cleanupTranscoder } from '$lib/api/maintenance';
	import BreadcrumbNav from '$lib/components/BreadcrumbNav.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import FileRow from '$lib/components/FileRow.svelte';
	import FilesTable from '$lib/components/FilesTable.svelte';
	import FilesToolbar from '$lib/components/FilesToolbar.svelte';
	import FileMoveDialog from '$lib/components/FileMoveDialog.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import OrphanFoldersModal from '$lib/components/OrphanFoldersModal.svelte';
	import { features } from '$lib/features';
	import NewFolderRow from '$lib/components/NewFolderRow.svelte';

	const browser = new FilesBrowser();
	const movePicker = new MovePicker(browser);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	// Delete confirmation (single item)
	let deleteDialog = $state({ open: false, root: '', subpath: '', name: '' });

	// Bulk delete confirmation
	let bulkDeleteOpen = $state(false);

	// New folder
	let creatingFolder = $state(false);
	let newFolderName = $state('');

	// Orphan folders modal
	const orphans = new OrphanFolders();

	// Transcoder cleanup
	let transcoderCleanupOpen = $state(false);

	function clearFeedback() {
		setTimeout(() => (feedback = null), 3000);
	}

	function showFeedback(next: BulkFeedback) {
		feedback = next;
		clearFeedback();
	}

	async function runWithFeedback(action: () => Promise<void>, fallback: string) {
		try {
			await action();
		} catch (e) {
			showFeedback({ type: 'error', message: errorMessage(e, fallback) });
		}
	}

	async function handleRename(entryName: string, newName: string) {
		await runWithFeedback(async () => {
			await renameFile(browser.current.root, browser.itemSubpath(entryName), newName);
			showFeedback({ type: 'success', message: `Renamed to ${newName}` });
			await browser.navigate(browser.current.root, browser.current.subpath);
		}, 'Rename failed');
	}

	async function handleFixPermissions(entryName: string, displayName: string) {
		await runWithFeedback(async () => {
			const result = await fixPermissions(browser.current.root, browser.itemSubpath(entryName));
			showFeedback({
				type: 'success',
				message: fixedPermissionsMessage(displayName, result.fixed)
			});
			await browser.navigate(browser.current.root, browser.current.subpath);
		}, 'Failed to fix permissions');
	}

	function handleDeleteRequest(entryName: string, displayName: string) {
		deleteDialog = {
			open: true,
			root: browser.current.root,
			subpath: browser.itemSubpath(entryName),
			name: displayName
		};
	}

	async function confirmDelete() {
		await runWithFeedback(async () => {
			await deleteFile(deleteDialog.root, deleteDialog.subpath);
			showFeedback({ type: 'success', message: `Deleted ${deleteDialog.name}` });
			deleteDialog = { open: false, root: '', subpath: '', name: '' };
			await browser.navigate(browser.current.root, browser.current.subpath);
		}, 'Delete failed');
	}

	// --- Bulk move with browsable picker ---
	async function confirmBulkMove() {
		let moved = 0;
		let failed = 0;
		for (const key of browser.selectedKeys) {
			const { root: srcRoot, subpath: srcSubpath } = parseSelectionKey(key);
			try {
				await moveFile(srcRoot, srcSubpath, movePicker.location.root, movePicker.location.subpath);
				moved++;
			} catch {
				failed++;
			}
		}
		movePicker.close();
		browser.selectedKeys = new Set();
		showFeedback(bulkResultFeedback('Moved', moved, failed));
		await browser.navigate(browser.current.root, browser.current.subpath);
	}

	// --- Bulk delete ---
	async function confirmBulkDelete() {
		let deleted = 0;
		let failed = 0;
		const items = orderForDelete([...browser.selectedKeys].map(parseSelectionKey));
		for (const item of items) {
			try {
				await deleteFile(item.root, item.subpath);
				deleted++;
			} catch {
				failed++;
			}
		}
		bulkDeleteOpen = false;
		browser.selectedKeys = new Set();
		showFeedback(bulkResultFeedback('Deleted', deleted, failed));
		await browser.navigate(browser.current.root, browser.current.subpath);
	}

	// --- New folder ---
	function startNewFolder() {
		newFolderName = '';
		creatingFolder = true;
	}

	async function confirmNewFolder() {
		if (!newFolderName.trim() || !browser.current.root) return;
		await runWithFeedback(async () => {
			await createDirectory(browser.current.root, browser.current.subpath, newFolderName.trim());
			showFeedback({ type: 'success', message: `Created folder "${newFolderName.trim()}"` });
			creatingFolder = false;
			newFolderName = '';
			await browser.navigate(browser.current.root, browser.current.subpath);
		}, 'Failed to create folder');
	}

	function cancelNewFolder() {
		creatingFolder = false;
		newFolderName = '';
	}

	// --- Transcoder cleanup ---
	async function handleCleanupTranscoder() {
		await runWithFeedback(async () => {
			const result = await cleanupTranscoder();
			showFeedback(cleanupFeedback(result.deleted, 'transcoder job', result.errors.length));
		}, 'Cleanup failed');
		transcoderCleanupOpen = false;
	}

	// React to ?root= and ?subpath= query param changes
	let lastParamKey = '';
	$effect(() => {
		const paramRoot = $page.url.searchParams.get('root');
		const paramSubpath = $page.url.searchParams.get('subpath') ?? '';
		if (paramRoot) {
			const key = `${paramRoot}::${paramSubpath}`;
			if (key !== lastParamKey) {
				lastParamKey = key;
				browser.navigate(paramRoot, paramSubpath);
			}
		}
	});

	onMount(async () => {
		await browser.loadRoots();
		const paramRoot = $page.url.searchParams.get('root');
		const paramSubpath = $page.url.searchParams.get('subpath') ?? '';
		if (paramRoot) {
			browser.current = { root: paramRoot, subpath: paramSubpath };
			lastParamKey = `${paramRoot}::${paramSubpath}`;
		}
		if (browser.current.root) {
			await browser.navigate(browser.current.root, browser.current.subpath);
		} else {
			browser.loading = false;
		}
	});
</script>

<svelte:head>
	<title>ARM - Files</title>
</svelte:head>

<div class="stack">
	<h1 class="page-title">Files</h1>

	<!-- Warning banner -->
	<div class="alert files-page-warning-banner" data-status="warning">
		<span class="alert-title">Warning:</span> Modify files at your own risk. This will not update database records and will
		cause issues for any in-progress rips or transcodes.
	</div>

	<!-- Feedback toast -->
	{#if feedback}
		<div class="alert files-page-feedback {feedback.type === 'success' ? 'alert-success' : 'alert-danger'}">
			{feedback.message}
		</div>
	{/if}

	<!-- Error -->
	{#if browser.error}
		<div class="alert alert-danger alert-lg">
			{browser.error}
		</div>
	{/if}

	<!-- Root tabs -->
	{#if browser.roots.length > 0}
		<div class="tabs" role="group" aria-label="File root tabs" data-file-roots>
			{#each browser.roots as root (root.key)}
				<button
					type="button"
					onclick={() => browser.navigate(root.key, '')}
					data-selected={root.key === browser.current.root}
					aria-pressed={root.key === browser.current.root}
					class="tabs-tab"
				>
					{root.label}
				</button>
			{/each}
		</div>
	{/if}

	<!-- Read-only mount banner -->
	{#if browser.isReadonly}
		<div class="alert alert-warning cluster files-page-readonly-banner">
			<svg
				class="h-4 w-4 shrink-0 files-page-readonly-icon"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
				stroke-width="2"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
				/>
			</svg>
			<p>This directory is on a read-only mount. File operations are disabled.</p>
		</div>
	{/if}

	<!-- Breadcrumb + toolbar row -->
	{#if browser.current.root && browser.roots.length > 0}
		<div class="flex items-center justify-between gap-3">
			<BreadcrumbNav
				root={browser.current.root}
				subpath={browser.current.subpath}
				roots={browser.roots}
				onnavigate={browser.navigate}
			/>
			<FilesToolbar
				{browser}
				onmove={movePicker.open}
				onbulkdelete={() => (bulkDeleteOpen = true)}
				onorphans={orphans.open}
				oncleanup={() => (transcoderCleanupOpen = true)}
				onnewfolder={startNewFolder}
			/>
		</div>
	{/if}

	<!-- File listing -->
	<LoadState
		data={browser.listing}
		loading={browser.loading && !browser.listing}
		error={browser.filesError}
		isEmpty={() => false}
	>
		{#snippet loadingSlot()}
			<div class="files-page-listing">
				<table class="table">
					<thead>
						<tr>
							<th class="table-header w-10"></th>
							<th class="table-header">Name</th>
							<th class="table-header files-page-cell-lg">Permissions</th>
							<th class="table-header table-right">Size</th>
							<th class="table-header files-page-cell-md">Modified</th>
							<th class="table-header table-right">Actions</th>
						</tr>
					</thead>
					<tbody>
						{#each Array(8) as _, i (i)}
							<FileRow />
						{/each}
					</tbody>
				</table>
			</div>
		{/snippet}
		{#snippet ready(lst)}
			<div class="files-page-listing">
				{#if lst.parent_subpath != null}
					<button
						type="button"
						onclick={() => browser.navigate(browser.current.root, lst.parent_subpath!)}
						class="flex w-full items-center gap-2 files-page-nav-row"
					>
						<span class="w-10"></span>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 17l-5-5m0 0l5-5m-5 5h12" />
						</svg>
						..
					</button>
				{/if}

				<!-- Inline new folder row -->
				{#if creatingFolder}
					<NewFolderRow bind:name={newFolderName} onconfirm={confirmNewFolder} oncancel={cancelNewFolder} />
				{/if}

				{#if browser.listing?.unavailable}
					<div class="files-page-empty">This root is not mounted on the server.</div>
				{:else if browser.sortedEntries.length === 0 && !creatingFolder}
					<div class="files-page-empty">This directory is empty</div>
				{:else if browser.sortedEntries.length > 0}
					<FilesTable
						{browser}
						onrename={handleRename}
						ondelete={handleDeleteRequest}
						onfixpermissions={handleFixPermissions}
					/>
				{/if}
			</div>
		{/snippet}
	</LoadState>
</div>

<!-- Delete confirmation -->
<ConfirmDialog
	open={deleteDialog.open}
	title="Delete {deleteDialog.name}"
	message="Are you sure you want to delete '{deleteDialog.name}'? This action cannot be undone."
	confirmLabel="Delete"
	variant="danger"
	onconfirm={confirmDelete}
	oncancel={() => (deleteDialog = { open: false, root: '', subpath: '', name: '' })}
/>

<!-- Bulk delete confirmation -->
<ConfirmDialog
	open={bulkDeleteOpen}
	title="Delete {browser.selectedKeys.size} {plural(browser.selectedKeys.size, 'item')}"
	message="This will permanently delete {browser.selectedKeys.size} selected item{browser.selectedKeys.size !== 1
		? 's'
		: ''}, including all contents of any folders. This cannot be undone."
	confirmLabel="Delete All"
	variant="danger"
	onconfirm={confirmBulkDelete}
	oncancel={() => (bulkDeleteOpen = false)}
/>

<!-- Transcoder cleanup confirmation -->
{#if features.maintenance}
	<ConfirmDialog
		open={transcoderCleanupOpen}
		title="Clean Up Transcoder"
		message="Delete all completed and failed transcoder jobs from the transcoder database?"
		confirmLabel="Clean Up"
		variant="danger"
		onconfirm={handleCleanupTranscoder}
		oncancel={() => (transcoderCleanupOpen = false)}
	/>
{/if}

<OrphanFoldersModal {orphans} />

<FileMoveDialog picker={movePicker} count={browser.selectedKeys.size} onconfirm={confirmBulkMove} />

<style>
	/* the original was bg-primary-light-bg/text-primary-dark (blue-100 /
	   blue-800, dark: 20% blue-900 / blue-400). Those legacy alias tokens are
	   gone (Task 13), so the banner sits on the nearest live roles: tint-2 is
	   a hair lighter than blue-100 and primary-text (blue-700 light /
	   blue-400 dark) a step lighter than blue-800; both mode-flip on their
	   own, which also retires the global dark-mode override. Named collapse. */
	/* original was px-4 py-3 (1rem/0.75rem), not .alert's own 0.5rem/0.75rem default */
	.files-page-warning-banner {
		padding: 0.75rem 1rem;
		background: var(--color-primary-tint-2);
		color: var(--color-primary-text);
	}
	/* original was px-4 py-2.5 (1rem/0.625rem), not .alert's own 0.5rem/0.75rem default */
	.files-page-readonly-banner {
		padding: 0.625rem 1rem;
	}
	/* original was px-4 py-2 (1rem/0.5rem) */
	.files-page-feedback {
		padding: 0.5rem 1rem;
	}
	.files-page-readonly-icon {
		color: var(--color-warning);
	}
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
	.files-page-listing {
		overflow: hidden;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
	}
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
	.files-page-empty {
		padding: 2rem;
		text-align: center;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
</style>
