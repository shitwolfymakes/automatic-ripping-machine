<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { fetchRoots, fetchDirectory, renameFile, moveFile, deleteFile, createDirectory, fixPermissions } from '$lib/api/files';
	import type { FileRoot, DirectoryListing } from '$lib/api/files';
	import { formatBytes, formatDateTime } from '$lib/utils/format';
	import { fetchOrphanFolders, deleteFolder as deleteOrphanFolder, bulkDeleteFolders, cleanupTranscoder } from '$lib/api/maintenance';
	import type { OrphanFoldersResponse } from '$lib/api/maintenance';
	import FileIcon from '$lib/components/FileIcon.svelte';
	import BreadcrumbNav from '$lib/components/BreadcrumbNav.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import FileRow from '$lib/components/FileRow.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import SortIndicator from '$lib/components/SortIndicator.svelte';
	import Glyph from '$lib/components/Glyph.svelte';

	let roots = $state<FileRoot[]>([]);
	// Current navigation position: root key + subpath within that root
	let current = $state<{ root: string; subpath: string }>({ root: '', subpath: '' });
	let listing = $state<DirectoryListing | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let filesError = $derived<Error | null>(error ? new Error(error) : null);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	// Sort state
	let sortKey = $state<'name' | 'size' | 'modified'>('name');
	let sortDir = $state<'asc' | 'desc'>('asc');

	// Selection state — key is `subpath/name` within the current root
	let selectedKeys = $state(new Set<string>());

	// Delete confirmation (single item)
	let deleteDialog = $state({ open: false, root: '', subpath: '', name: '' });

	// Bulk delete confirmation
	let bulkDeleteOpen = $state(false);

	// Move dialog — browsable directory picker
	let moveDialogOpen = $state(false);
	let picker = $state<{ root: string; subpath: string }>({ root: '', subpath: '' });
	let pickerListing = $state<DirectoryListing | null>(null);
	let pickerLoading = $state(false);

	// New folder
	let creatingFolder = $state(false);
	let newFolderName = $state('');

	// Orphan folders modal
	let orphanFoldersOpen = $state(false);
	let orphanFoldersData = $state<OrphanFoldersResponse | null>(null);
	let orphanFoldersLoading = $state(false);
	let orphanFoldersSelected = $state<Set<string>>(new Set());
	let orphanFoldersBusy = $state(false);
	let orphanFoldersFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	// Transcoder cleanup
	let transcoderCleanupOpen = $state(false);
	let transcoderBusy = $state(false);

	let isReadonly = $derived(listing?.readonly === true);

	let sortedEntries = $derived.by(() => {
		if (!listing) return [];
		return [...listing.entries].sort((a, b) => {
			if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
			let cmp: number;
			if (sortKey === 'size') {
				cmp = (a.size ?? 0) - (b.size ?? 0);
			} else if (sortKey === 'modified') {
				cmp = (a.modified ?? '').localeCompare(b.modified ?? '');
			} else {
				cmp = a.name.toLowerCase().localeCompare(b.name.toLowerCase());
			}
			return sortDir === 'asc' ? cmp : -cmp;
		});
	});

	// Build the item subpath for a named entry in the current directory
	function itemSubpath(entryName: string): string {
		return current.subpath ? `${current.subpath}/${entryName}` : entryName;
	}

	// Build a selection key (root::subpath) for an entry
	function selectionKey(entryName: string): string {
		return `${current.root}::${itemSubpath(entryName)}`;
	}

	// Subfolders in the picker (excluding items being moved)
	let pickerFolders = $derived.by(() => {
		if (!pickerListing) return [];
		// Only exclude selected folders when the picker is browsing the same dir as the source.
		// When the picker is in a different dir, none of the source selection applies.
		const sameDir = picker.root === current.root && picker.subpath === current.subpath;
		const movingNames = sameDir
			? new Set([...selectedKeys].map((k) => k.split('::')[1].split('/').pop()))
			: new Set<string | undefined>();
		return pickerListing.entries.filter(
			(e) => e.type === 'directory' && !movingNames.has(e.name)
		);
	});

	// Can we go up from picker?
	let pickerCanGoUp = $derived(
		picker.subpath !== '' || picker.root !== current.root
	);

	let allSelected = $derived(
		sortedEntries.length > 0 &&
		sortedEntries.every(e => selectedKeys.has(selectionKey(e.name)))
	);

	function toggleSort(key: 'name' | 'size' | 'modified') {
		if (sortKey === key) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortKey = key;
			sortDir = key === 'modified' ? 'desc' : 'asc';
		}
	}

	function sortIconDir(key: string): 'asc' | 'desc' | null {
		if (sortKey !== key) return null;
		return sortDir;
	}

	function clearFeedback() {
		setTimeout(() => (feedback = null), 3000);
	}

	function toggleSelect(entryName: string) {
		const key = selectionKey(entryName);
		const next = new Set(selectedKeys);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		selectedKeys = next;
	}

	function toggleSelectAll() {
		if (!listing) return;
		if (allSelected) {
			selectedKeys = new Set();
		} else {
			selectedKeys = new Set(sortedEntries.map(e => selectionKey(e.name)));
		}
	}

	const rootOrder: Record<string, number> = { raw: 0, transcode: 1, completed: 2, music: 3 };

	async function loadRoots() {
		try {
			roots = (await fetchRoots()).sort((a, b) => (rootOrder[a.key ?? ''] ?? 99) - (rootOrder[b.key ?? ''] ?? 99));
			if (roots.length > 0 && !current.root) {
				current = { root: roots[0].key, subpath: '' };
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load roots';
		}
	}

	async function navigate(root: string, subpath: string) {
		loading = true;
		error = null;
		current = { root, subpath };
		selectedKeys = new Set();
		try {
			listing = await fetchDirectory(root, subpath);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load directory';
			listing = null;
		} finally {
			loading = false;
		}
	}

	async function handleRename(entryName: string, newName: string) {
		try {
			await renameFile(current.root, itemSubpath(entryName), newName);
			feedback = { type: 'success', message: `Renamed to ${newName}` };
			clearFeedback();
			await navigate(current.root, current.subpath);
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Rename failed' };
			clearFeedback();
		}
	}

	async function handleFixPermissions(entryName: string, displayName: string) {
		try {
			const result = await fixPermissions(current.root, itemSubpath(entryName));
			feedback = { type: 'success', message: `Fixed permissions on ${displayName} (${result.fixed} item${result.fixed !== 1 ? 's' : ''})` };
			clearFeedback();
			await navigate(current.root, current.subpath);
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Failed to fix permissions' };
			clearFeedback();
		}
	}

	function handleDeleteRequest(entryName: string, displayName: string) {
		deleteDialog = { open: true, root: current.root, subpath: itemSubpath(entryName), name: displayName };
	}

	async function confirmDelete() {
		try {
			await deleteFile(deleteDialog.root, deleteDialog.subpath);
			feedback = { type: 'success', message: `Deleted ${deleteDialog.name}` };
			clearFeedback();
			deleteDialog = { open: false, root: '', subpath: '', name: '' };
			await navigate(current.root, current.subpath);
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Delete failed' };
			clearFeedback();
		}
	}

	// --- Bulk move with browsable picker ---
	async function openMoveDialog() {
		if (selectedKeys.size === 0) return;
		picker = { root: current.root, subpath: current.subpath };
		moveDialogOpen = true;
		await loadPickerLocation(current.root, current.subpath);
	}

	async function loadPickerLocation(root: string, subpath: string) {
		pickerLoading = true;
		try {
			pickerListing = await fetchDirectory(root, subpath);
			picker = { root, subpath };
		} catch {
			// stay on current listing
		} finally {
			pickerLoading = false;
		}
	}

	async function pickerNavigate(root: string, subpath: string) {
		await loadPickerLocation(root, subpath);
	}

	async function pickerGoUp() {
		if (!pickerCanGoUp) return;
		if (pickerListing?.parent_subpath != null) {
			// go up within the same root
			await loadPickerLocation(picker.root, pickerListing.parent_subpath);
		} else if (picker.subpath === '') {
			// already at root of this root key — nothing to do (root switching not in picker)
		}
	}

	function closeMoveDialog() {
		moveDialogOpen = false;
		pickerListing = null;
	}

	function pickerDisplayPath(): string {
		const rootObj = roots.find(r => r.key === picker.root);
		const rootLabel = rootObj?.label ?? picker.root;
		if (!picker.subpath) return rootLabel;
		return `${rootLabel}/${picker.subpath}`;
	}

	async function confirmBulkMove() {
		let moved = 0;
		let failed = 0;
		for (const key of selectedKeys) {
			const [srcRoot, srcSubpath] = key.split('::');
			try {
				await moveFile(srcRoot, srcSubpath, picker.root, picker.subpath);
				moved++;
			} catch {
				failed++;
			}
		}
		closeMoveDialog();
		selectedKeys = new Set();
		if (failed > 0) {
			feedback = { type: 'error', message: `Moved ${moved}, failed ${failed}` };
		} else {
			feedback = { type: 'success', message: `Moved ${moved} item${moved !== 1 ? 's' : ''}` };
		}
		clearFeedback();
		await navigate(current.root, current.subpath);
	}

	// --- Bulk delete ---
	async function confirmBulkDelete() {
		let deleted = 0;
		let failed = 0;
		// Sort by subpath length descending so children are deleted before parents
		const items = [...selectedKeys]
			.map(k => { const [r, sp] = k.split('::'); return { root: r, subpath: sp }; })
			.sort((a, b) => b.subpath.length - a.subpath.length);
		const deletedSubpaths: string[] = [];
		for (const item of items) {
			if (deletedSubpaths.some((dp) => item.subpath.startsWith(dp + '/'))) {
				deleted++;
				continue;
			}
			try {
				await deleteFile(item.root, item.subpath);
				deleted++;
				deletedSubpaths.push(item.subpath);
			} catch {
				failed++;
			}
		}
		bulkDeleteOpen = false;
		selectedKeys = new Set();
		if (failed > 0) {
			feedback = { type: 'error', message: `Deleted ${deleted}, failed ${failed}` };
		} else {
			feedback = { type: 'success', message: `Deleted ${deleted} item${deleted !== 1 ? 's' : ''}` };
		}
		clearFeedback();
		await navigate(current.root, current.subpath);
	}

	// --- New folder ---
	function startNewFolder() {
		newFolderName = '';
		creatingFolder = true;
	}

	async function confirmNewFolder() {
		if (!newFolderName.trim() || !current.root) return;
		try {
			await createDirectory(current.root, current.subpath, newFolderName.trim());
			feedback = { type: 'success', message: `Created folder "${newFolderName.trim()}"` };
			clearFeedback();
			creatingFolder = false;
			newFolderName = '';
			await navigate(current.root, current.subpath);
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Failed to create folder' };
			clearFeedback();
		}
	}

	function cancelNewFolder() {
		creatingFolder = false;
		newFolderName = '';
	}

	function handleNewFolderKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') confirmNewFolder();
		if (e.key === 'Escape') cancelNewFolder();
	}

	// --- Orphan folders ---
	async function openOrphanFoldersModal() {
		orphanFoldersOpen = true;
		orphanFoldersLoading = true;
		orphanFoldersFeedback = null;
		try {
			orphanFoldersData = await fetchOrphanFolders();
			orphanFoldersSelected = new Set();
		} catch { orphanFoldersData = null; }
		orphanFoldersLoading = false;
	}

	function toggleOrphanFolderSelect(path: string) {
		const next = new Set(orphanFoldersSelected);
		if (next.has(path)) next.delete(path);
		else next.add(path);
		orphanFoldersSelected = next;
	}

	async function handleDeleteOrphanFolder(path: string) {
		const name = path.split('/').pop();
		orphanFoldersBusy = true;
		try {
			await deleteOrphanFolder(path);
			orphanFoldersFeedback = { type: 'success', message: `Folder "${name}" deleted` };
			orphanFoldersData = await fetchOrphanFolders();
			orphanFoldersSelected = new Set();
		} catch (e) {
			orphanFoldersFeedback = { type: 'error', message: e instanceof Error ? e.message : 'Delete failed' };
		}
		orphanFoldersBusy = false;
	}

	async function handleBulkDeleteOrphanFolders() {
		orphanFoldersBusy = true;
		try {
			const result = await bulkDeleteFolders([...orphanFoldersSelected]);
			orphanFoldersFeedback = {
				type: result.errors.length ? 'error' : 'success',
				message: `Deleted ${result.removed.length} folder${result.removed.length !== 1 ? 's' : ''}${result.errors.length ? `, ${result.errors.length} error(s)` : ''}`
			};
			orphanFoldersData = await fetchOrphanFolders();
			orphanFoldersSelected = new Set();
		} catch (e) {
			orphanFoldersFeedback = { type: 'error', message: e instanceof Error ? e.message : 'Bulk delete failed' };
		}
		orphanFoldersBusy = false;
	}

	// --- Transcoder cleanup ---
	async function handleCleanupTranscoder() {
		transcoderBusy = true;
		try {
			const result = await cleanupTranscoder();
			feedback = {
				type: result.errors.length ? 'error' : 'success',
				message: `Deleted ${result.deleted} transcoder job${result.deleted !== 1 ? 's' : ''}${result.errors.length ? `, ${result.errors.length} error(s)` : ''}`
			};
			clearFeedback();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Cleanup failed' };
			clearFeedback();
		}
		transcoderBusy = false;
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
				navigate(paramRoot, paramSubpath);
			}
		}
	});

	onMount(async () => {
		await loadRoots();
		const paramRoot = $page.url.searchParams.get('root');
		const paramSubpath = $page.url.searchParams.get('subpath') ?? '';
		if (paramRoot) {
			current = { root: paramRoot, subpath: paramSubpath };
			lastParamKey = `${paramRoot}::${paramSubpath}`;
		}
		if (current.root) {
			await navigate(current.root, current.subpath);
		} else {
			loading = false;
		}
	});
</script>

{#snippet sortIcon(key: string)}
	<SortIndicator dir={sortIconDir(key)} />
{/snippet}

<svelte:head>
	<title>ARM - Files</title>
</svelte:head>

<div class="stack">
	<h1 class="page-title">Files</h1>

	<!-- Warning banner -->
	<div class="alert files-page-warning-banner">
		<span class="alert-title">Warning:</span> Modify files at your own risk. This will not update database records and will cause issues for any in-progress rips or transcodes.
	</div>

	<!-- Feedback toast -->
	{#if feedback}
		<div class="alert files-page-feedback {feedback.type === 'success' ? 'alert-success' : 'alert-danger'}">
			{feedback.message}
		</div>
	{/if}

	<!-- Error -->
	{#if error}
		<div class="alert alert-danger alert-lg">
			{error}
		</div>
	{/if}

	<!-- Root tabs -->
	{#if roots.length > 0}
		<div class="tabs" aria-label="File root tabs">
			{#each roots as root}
				<button
					type="button"
					onclick={() => navigate(root.key, '')}
					data-selected={root.key === current.root}
					class="tabs-tab"
				>
					{root.label}
				</button>
			{/each}
		</div>
	{/if}

	<!-- Read-only mount banner -->
	{#if isReadonly}
		<div class="alert alert-warning cluster files-page-readonly-banner">
			<svg class="h-4 w-4 shrink-0 files-page-readonly-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
			</svg>
			<p>This directory is on a read-only mount. File operations are disabled.</p>
		</div>
	{/if}

	<!-- Breadcrumb + toolbar row -->
	{#if current.root && roots.length > 0}
		<div class="flex items-center justify-between gap-3">
			<BreadcrumbNav root={current.root} subpath={current.subpath} {roots} onnavigate={navigate} />
			<div class="cluster shrink-0 files-page-toolbar">
				<!-- Bulk move (visible when items selected) -->
				{#if selectedKeys.size > 0 && $isAdmin}
					<button
						type="button"
						onclick={openMoveDialog}
						disabled={isReadonly}
						class="btn btn-primary files-page-bulk-btn"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
						</svg>
						Move {selectedKeys.size}
					</button>
					<button
						type="button"
						onclick={() => (bulkDeleteOpen = true)}
						disabled={isReadonly}
						class="btn files-page-bulk-btn files-page-bulk-btn-danger"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
						</svg>
						Delete {selectedKeys.size}
					</button>
				{/if}
				{#if $isAdmin}
					<!-- Orphan folders -->
					<button
						type="button"
						onclick={openOrphanFoldersModal}
						class="btn btn-icon files-page-toolbar-btn"
						title="Orphan folders"
					>
						<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 11v4m-2-2h4" />
						</svg>
					</button>
					<!-- Transcoder cleanup -->
					<button
						type="button"
						onclick={() => (transcoderCleanupOpen = true)}
						class="btn btn-icon files-page-toolbar-btn"
						title="Clean up transcoder jobs"
					>
						<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" />
						</svg>
					</button>
				{/if}
				<!-- New folder -->
				{#if $isAdmin}
					<button
						type="button"
						onclick={startNewFolder}
						disabled={isReadonly}
						class="btn btn-icon files-page-toolbar-btn"
						title={isReadonly ? 'Read-only mount' : 'New folder'}
					>
						<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
						</svg>
					</button>
				{/if}
				<!-- Refresh -->
				<button
					type="button"
					onclick={() => navigate(current.root, current.subpath)}
				disabled={loading}
				class="btn btn-icon files-page-toolbar-btn"
				title="Refresh"
				>
					<svg class="h-5 w-5 {loading ? 'spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
					</svg>
				</button>
			</div>
		</div>
	{/if}

	<!-- File listing -->
	<LoadState
		data={listing}
		loading={loading && !listing}
		error={filesError}
		isEmpty={() => false}
		transitionKey={`files-${current.root}-${current.subpath}`}
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
						{#each Array(8) as _}
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
						onclick={() => navigate(current.root, lst.parent_subpath!)}
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
					<div class="flex items-center gap-2 files-page-nav-row files-page-new-folder-row">
						<span class="w-10"></span>
						<svg class="h-5 w-5 shrink-0 files-page-folder-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
						</svg>
						<input
							type="text"
							bind:value={newFolderName}
							onkeydown={handleNewFolderKeydown}
							placeholder="Folder name"
							class="field-control flex-1 files-page-new-folder-input"
						/>
						<button type="button" onclick={confirmNewFolder} class="btn btn-icon files-page-new-folder-confirm" title="Create">
							<Glyph name="check" />
						</button>
						<button type="button" onclick={cancelNewFolder} class="btn btn-icon" title="Cancel">
							<Glyph name="x" />
						</button>
					</div>
				{/if}

				{#if listing?.unavailable}
					<div class="files-page-empty">
						This root is not mounted on the server.
					</div>
				{:else if sortedEntries.length === 0 && !creatingFolder}
					<div class="files-page-empty">
						This directory is empty
					</div>
				{:else if sortedEntries.length > 0}
					<table class="table">
						<thead>
							<tr>
								<th class="table-header w-10">
									{#if $isAdmin}
										<input
											type="checkbox"
											checked={allSelected}
											onchange={toggleSelectAll}
											class="files-page-select-all"
										/>
									{/if}
								</th>
								<th class="table-header">
									<button type="button" onclick={() => toggleSort('name')} class="files-page-sort-btn">
										Name {@render sortIcon('name')}
									</button>
								</th>
								<th class="table-header files-page-cell-lg">Permissions</th>
								<th class="table-header table-right">
									<button type="button" onclick={() => toggleSort('size')} class="files-page-sort-btn">
										Size {@render sortIcon('size')}
									</button>
								</th>
								<th class="table-header files-page-cell-md">
									<button type="button" onclick={() => toggleSort('modified')} class="files-page-sort-btn">
										Modified {@render sortIcon('modified')}
									</button>
								</th>
								<th class="table-header table-right">Actions</th>
							</tr>
						</thead>
						<tbody>
							{#each sortedEntries as entry (entry.name)}
								<FileRow
									{entry}
									currentPath={current.subpath}
									selected={selectedKeys.has(selectionKey(entry.name))}
									readonly={isReadonly}
									showActions={$isAdmin}
									onnavigate={() => navigate(current.root, itemSubpath(entry.name))}
									onrename={(_, newName) => handleRename(entry.name, newName)}
									ondelete={(_, name) => handleDeleteRequest(entry.name, name)}
									ontoggle={() => toggleSelect(entry.name)}
									onfixpermissions={(_, name) => handleFixPermissions(entry.name, name)}
								/>
							{/each}
						</tbody>
					</table>
				{/if}
			</div>
		{/snippet}
		{#snippet empty()}
			<div class="panel files-page-empty-panel">
				<p class="files-page-empty-panel-text">No media directories configured</p>
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
	title="Delete {selectedKeys.size} item{selectedKeys.size !== 1 ? 's' : ''}"
	message="This will permanently delete {selectedKeys.size} selected item{selectedKeys.size !== 1 ? 's' : ''}, including all contents of any folders. This cannot be undone."
	confirmLabel="Delete All"
	variant="danger"
	onconfirm={confirmBulkDelete}
	oncancel={() => (bulkDeleteOpen = false)}
/>

<!-- Transcoder cleanup confirmation -->
<ConfirmDialog
	open={transcoderCleanupOpen}
	title="Clean Up Transcoder"
	message="Delete all completed and failed transcoder jobs from the transcoder database?"
	confirmLabel="Clean Up"
	variant="danger"
	onconfirm={handleCleanupTranscoder}
	oncancel={() => (transcoderCleanupOpen = false)}
/>

<!-- Orphan folders modal -->
{#if orphanFoldersOpen}
	<div class="modal">
		<button
			type="button"
			class="modal-backdrop files-page-modal-backdrop"
			aria-label="Close dialog"
			onclick={() => (orphanFoldersOpen = false)}
		></button>
		<div class="modal-panel files-page-orphan-panel">
			<!-- Header -->
			<div class="shrink-0 files-page-modal-header">
				<h3 class="modal-title">Orphan Folders</h3>
				<p class="files-page-modal-subtitle">Folders not associated with any job</p>
			</div>

			<!-- Feedback -->
			{#if orphanFoldersFeedback}
				<div class="shrink-0 files-page-modal-feedback-row">
					<div class="alert files-page-orphan-feedback {orphanFoldersFeedback.type === 'success' ? 'alert-success' : 'alert-danger'}">
						{orphanFoldersFeedback.message}
					</div>
				</div>
			{/if}

			<!-- Content (scrollable) -->
			<div class="min-h-0 flex-1 overflow-y-auto">
				{#if orphanFoldersLoading}
					<div class="flex items-center justify-center p-8">
						<svg class="mr-2 h-5 w-5 spin files-page-spinner" viewBox="0 0 24 24">
							<circle class="spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
							<path class="spinner-fill" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
						</svg>
						<span class="files-page-loading-text">Loading...</span>
					</div>
				{:else if orphanFoldersData && orphanFoldersData.folders.length > 0}
					{#each orphanFoldersData.folders as folder (folder.path)}
						<div class="list-row files-page-orphan-row">
							<input
								type="checkbox"
								checked={orphanFoldersSelected.has(folder.path)}
								onchange={() => toggleOrphanFolderSelect(folder.path)}
								disabled={orphanFoldersBusy}
								class="files-page-select-all"
							/>
							<svg class="h-5 w-5 shrink-0 files-page-folder-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
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
								onclick={() => handleDeleteOrphanFolder(folder.path)}
								disabled={orphanFoldersBusy}
								class="btn btn-icon files-page-orphan-delete"
								title="Delete folder"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
								</svg>
							</button>
						</div>
					{/each}
				{:else if orphanFoldersData}
					<div class="files-page-empty">
						No orphan folders found
					</div>
				{:else}
					<div class="files-page-empty files-page-empty-error">
						Failed to load orphan folders
					</div>
				{/if}
			</div>

			<!-- Footer -->
			<div class="shrink-0 files-page-modal-footer">
				<div class="flex items-center justify-between">
					<div>
						{#if orphanFoldersSelected.size > 0}
							<button
								type="button"
								onclick={handleBulkDeleteOrphanFolders}
								disabled={orphanFoldersBusy}
								class="btn files-page-bulk-btn files-page-bulk-btn-danger"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
								</svg>
								Delete {orphanFoldersSelected.size} selected
							</button>
						{/if}
					</div>
					<button
						type="button"
						onclick={() => (orphanFoldersOpen = false)}
						class="btn"
					>
						Close
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- Bulk move dialog — browsable directory picker -->
{#if moveDialogOpen}
	<div class="modal">
		<button
			type="button"
			class="modal-backdrop files-page-modal-backdrop"
			aria-label="Close dialog"
			onclick={closeMoveDialog}
		></button>
		<div class="modal-panel files-page-orphan-panel">
			<!-- Header -->
			<div class="shrink-0 files-page-modal-header">
				<h3 class="modal-title">
					Move {selectedKeys.size} item{selectedKeys.size !== 1 ? 's' : ''}
				</h3>
				<p class="files-page-modal-subtitle">
					Browse to the destination folder
				</p>
			</div>

			<!-- Current picker location -->
			<div class="shrink-0 files-page-picker-location">
				<div class="flex items-center gap-2 files-page-picker-location-text">
					<svg class="h-4 w-4 shrink-0 files-page-folder-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
					</svg>
					<span class="files-page-picker-path">{pickerDisplayPath()}</span>
					{#if picker.root === current.root && picker.subpath === current.subpath}
						<span class="badge files-page-current-badge">current</span>
					{/if}
				</div>
			</div>

			<!-- Folder list (scrollable) -->
			<div class="min-h-0 flex-1 overflow-y-auto">
				{#if pickerLoading}
					<div class="flex items-center justify-center p-8">
						<svg class="mr-2 h-5 w-5 spin files-page-spinner" viewBox="0 0 24 24">
							<circle class="spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
							<path class="spinner-fill" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
						</svg>
					</div>
				{:else}
					<!-- Go up -->
					{#if pickerCanGoUp}
						<button
							type="button"
							onclick={pickerGoUp}
							class="flex w-full items-center gap-3 files-page-picker-row"
						>
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 17l-5-5m0 0l5-5m-5 5h12" />
							</svg>
							..
						</button>
					{/if}

					{#if pickerFolders.length === 0 && !pickerCanGoUp}
						<div class="files-page-picker-empty">
							No subfolders
						</div>
					{/if}

					{#each pickerFolders as folder (folder.name)}
						<button
							type="button"
							onclick={() => pickerNavigate(picker.root, picker.subpath ? `${picker.subpath}/${folder.name}` : folder.name)}
							class="flex w-full items-center gap-3 files-page-picker-row files-page-picker-row-folder"
						>
							<svg class="h-5 w-5 shrink-0 files-page-folder-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
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
					<button
						type="button"
						onclick={closeMoveDialog}
						class="btn"
					>
						Cancel
					</button>
					<button
						type="button"
						onclick={confirmBulkMove}
						disabled={picker.root === current.root && picker.subpath === current.subpath}
						class="btn btn-primary"
						title={picker.root === current.root && picker.subpath === current.subpath ? 'Navigate to a different folder first' : ''}
					>
						Move here
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	/* the original was bg-primary-light-bg/text-primary-dark (blue-100 /
	   blue-800, dark: 20% blue-900 / blue-400). Those legacy alias tokens are
	   gone (Task 13), so the banner sits on the nearest live roles: tint-2 is
	   a hair lighter than blue-100 and primary-text (blue-700 light /
	   blue-400 dark) a step lighter than blue-800; both mode-flip on their
	   own, which also retires the global dark-mode override. Named collapse. */
	/* original was px-4 py-3 (1rem/0.75rem), not .alert's own 0.5rem/0.75rem default */
	.files-page-warning-banner { padding: 0.75rem 1rem; background: var(--color-primary-tint-2); color: var(--color-primary-text); }
	/* original was px-4 py-2.5 (1rem/0.625rem), not .alert's own 0.5rem/0.75rem default */
	.files-page-readonly-banner { padding: 0.625rem 1rem; }
	/* original was px-4 py-2 (1rem/0.5rem) */
	.files-page-feedback { padding: 0.5rem 1rem; }
	/* original was px-3 py-1.5 (0.75rem/0.375rem) */
	.files-page-orphan-feedback { padding: 0.375rem 0.75rem; }
	.files-page-readonly-icon { color: var(--color-warning); }
	.files-page-toolbar { gap: 0.25rem; }
	/* original was rounded-lg p-2 (0.5rem all around), not .btn-icon's own
	   0.375rem default - a real ~4px-per-side layout regression */
	.files-page-toolbar-btn { padding: 0.5rem; }
	/* replaces the banned inline `hidden lg:table-cell`/`hidden
	   md:table-cell` (table/table-row/table-cell are Tailwind
	   display-utility names, banned outright by the lint per Task 11 fix
	   round 3 - only the table block's own classes may set that display
	   value) */
	.files-page-cell-lg { display: none; }
	@media (min-width: 1024px) {
		.files-page-cell-lg { display: table-cell; }
	}
	.files-page-cell-md { display: none; }
	@media (min-width: 768px) {
		.files-page-cell-md { display: table-cell; }
	}
	/* original bulk-action buttons were px-3 py-1.5 text-xs (0.75rem/1rem),
	   smaller than .btn's own default 1rem/0.5rem/text-sm - restated to
	   match; the icon+label gap (gap-1.5) is close enough to .btn's own
	   0.375rem default that no override is needed there */
	.files-page-bulk-btn { padding: 0.375rem 0.75rem; font-size: 0.75rem; line-height: 1rem; }
	.files-page-bulk-btn-danger { border: 0; background: var(--color-danger); color: var(--color-on-primary); }
	/* darkens on hover like the original's bg-red-600 -> hover:bg-red-700;
	   no darker danger token exists, so filter substitutes for a literal
	   colour (the lint bans raw colour keywords, even inside color-mix) */
	.files-page-bulk-btn-danger:hover { filter: brightness(0.9); }
	.files-page-listing { overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); }
	.files-page-nav-row { border-bottom: 1px solid var(--color-border); padding: 0.5rem 0.75rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-secondary); }
	.files-page-nav-row:hover { background: var(--color-primary-tint-1); }
	.files-page-new-folder-row { background: var(--color-primary-tint-1); }
	.files-page-new-folder-input { width: auto; min-height: auto; padding: 0.25rem 0.5rem; }
	.files-page-folder-icon { color: var(--color-warning); }
	.files-page-new-folder-confirm { color: var(--color-success); }
	.files-page-new-folder-confirm:hover { background: var(--color-success-soft); color: var(--color-success); }
	.files-page-empty { padding: 2rem; text-align: center; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.files-page-empty-panel { padding: 2rem; text-align: center; }
	.files-page-empty-panel-text { color: var(--color-text-muted); }
	.files-page-select-all { height: 1rem; width: 1rem; border-radius: var(--radius-sm); border: 1px solid var(--color-border-strong); accent-color: var(--color-primary); }
	.files-page-sort-btn { color: inherit; }
	.files-page-sort-btn:hover { color: var(--color-text-secondary); }
	.files-page-modal-backdrop { position: absolute; inset: 0; }
	.files-page-orphan-panel { display: flex; width: 100%; max-width: 32rem; max-height: 80vh; flex-direction: column; padding: 0; }
	.files-page-modal-header { border-bottom: 1px solid var(--color-border); padding: 1rem 1.5rem; }
	.files-page-modal-subtitle { margin-top: 0.25rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.files-page-modal-feedback-row { border-bottom: 1px solid var(--color-border); padding: 0.5rem 1.5rem; }
	.files-page-spinner { color: var(--color-text-faint); }
	.files-page-loading-text { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	/* the original row was a plain flex row (no hover/pointer affordance -
	   only its checkbox/delete button are interactive); list-row's own
	   cursor:pointer/hover-tint are for a clickable row and don't apply here */
	.files-page-orphan-row { grid-template-columns: auto auto 1fr auto auto; gap: 0.75rem; padding: 0.625rem 1.5rem; cursor: default; }
	.files-page-orphan-row:hover { background: transparent; }
	.files-page-orphan-name { font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text); }
	.files-page-orphan-size { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	/* the original category pill used two literal hues with no shared
	   badge look (rounded-full px-2 py-0.5 text-xs font-medium); nearest
	   tones are warning (raw) and success (completed) */
	.files-page-category-badge { border-radius: 9999px; }
	.files-page-category-badge[data-category="raw"] { background: var(--color-warning-soft); color: var(--color-on-warning-soft); }
	.files-page-category-badge[data-category="completed"] { background: var(--color-success-soft); color: var(--color-on-success-soft); }
	.files-page-orphan-delete { color: var(--color-danger); }
	.files-page-orphan-delete:hover { background: var(--color-danger-soft); color: var(--color-danger); }
	.files-page-modal-footer { border-top: 1px solid var(--color-border); padding: 1rem 1.5rem; }
	.files-page-picker-location { border-bottom: 1px solid var(--color-border); background: var(--color-page); padding: 0.5rem 1.5rem; }
	.files-page-picker-location-text { font-size: 0.875rem; line-height: 1.25rem; }
	.files-page-picker-path { font-weight: 500; color: var(--color-text); }
	/* original was a plain lowercase gray-200/gray-600 tag, not .badge's
	   primary-tinted pill nor .badge-sm's uppercase transform - no neutral
	   token exists (spec 5.1), so this keeps .badge's shape (pill, weight,
	   size) but restates the case and a text-sm-scale padding */
	.files-page-current-badge { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-size: 0.75rem; line-height: 1rem; text-transform: none; letter-spacing: normal; }
	.files-page-picker-row { border-bottom: 1px solid var(--color-border); padding: 0.625rem 1.5rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-secondary); }
	.files-page-picker-row:hover { background: var(--color-primary-tint-1); }
	.files-page-picker-row-folder { color: var(--color-text); }
	.files-page-picker-empty { padding: 1.5rem; text-align: center; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	/* :global: forwarded through Glyph's class prop */
	:global(.files-page-chevron) { color: var(--color-text-faint); }
</style>
