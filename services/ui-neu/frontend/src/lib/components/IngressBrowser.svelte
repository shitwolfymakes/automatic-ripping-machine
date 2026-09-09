<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { fetchIngressRoot, fetchIngressDirectory } from '$lib/api/import-jobs';
	import { showImportWizard } from '$lib/stores/importWizard';
	import type { FileEntry } from '$lib/api/files';
	import { Folder, FolderArchive, Disc, File as FileIcon } from 'lucide-svelte';
	import SortIndicator from '$lib/components/SortIndicator.svelte';

	// NOTE: kind/importable are computed client-side until the BFF (arm-neu PR #333)
	// emits them per entry. Once the BFF lands those fields and api.gen.ts picks
	// them up via codegen, this fallback computation can be replaced by direct
	// reads of entry.kind / entry.importable.
	type EntryKind = 'dir' | 'iso' | 'other';

	interface DecoratedEntry extends FileEntry {
		kind: EntryKind;
		importable: boolean;
	}

	interface Props {
		onselect: (selection: { path: string; kind: 'dir' | 'iso' }) => void;
	}

	let { onselect }: Props = $props();

	let ingressPath = $state<string | null>(null);
	let currentPath = $state('');
	let entries = $state<FileEntry[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let needsConfig = $state(false);
	let selectedPath = $state<string | null>(null);
	let filter = $state('');
	let scrollContainer = $state<HTMLDivElement | null>(null);
	let sortKey = $state<'name' | 'size' | 'modified'>('name');
	let sortDir = $state<'asc' | 'desc'>('asc');

	function classifyEntry(entry: FileEntry, allEntries: readonly FileEntry[]): { kind: EntryKind; importable: boolean } {
		// Prefer server-computed fields when present; codegen may not yet expose them.
		const raw = entry as FileEntry & { kind?: EntryKind; importable?: boolean };
		if (raw.kind) {
			return { kind: raw.kind, importable: raw.importable ?? false };
		}
		if (entry.type === 'directory') {
			// A folder is importable when it (or a sibling, in the disc-internal case)
			// contains BDMV/VIDEO_TS. We can only see siblings so the importable signal
			// here is heuristic: a top-level dir is treated as potentially importable
			// (true) and the user discovers the actual disc structure on the next nav.
			// Disc-structure internals (BDMV/VIDEO_TS themselves) are still flagged via
			// the existing isDiscStructureDir helper and rendered greyed.
			return { kind: 'dir', importable: true };
		}
		if (entry.name.toLowerCase().endsWith('.iso')) {
			return { kind: 'iso', importable: true };
		}
		return { kind: 'other', importable: false };
	}

	let decoratedEntries = $derived<DecoratedEntry[]>(
		entries.map((e) => ({ ...e, ...classifyEntry(e, entries) }))
	);

	let visibleEntries = $derived(
		decoratedEntries.filter((e) => e.kind === 'dir' || e.kind === 'iso' || e.kind === 'other')
	);

	let allDirectories = $derived(visibleEntries.filter((e) => e.kind === 'dir'));
	let filterEnabled = $derived(visibleEntries.length > 5);
	let sortedEntries = $derived(
		[...visibleEntries]
			.filter((e) => !filter || e.name.toLowerCase().includes(filter.toLowerCase()))
			.sort((a, b) => {
				let cmp: number;
				if (sortKey === 'size') cmp = (a.size ?? 0) - (b.size ?? 0);
				else if (sortKey === 'modified') cmp = (a.modified ?? '').localeCompare(b.modified ?? '');
				else cmp = a.name.toLowerCase().localeCompare(b.name.toLowerCase());
				return sortDir === 'asc' ? cmp : -cmp;
			})
	);

	function toggleSort(key: 'name' | 'size' | 'modified') {
		if (sortKey === key) { sortDir = sortDir === 'asc' ? 'desc' : 'asc'; }
		else { sortKey = key; sortDir = key === 'modified' ? 'desc' : 'asc'; }
	}

	function sortIconDir(key: string): 'asc' | 'desc' | null {
		if (sortKey !== key) return null;
		return sortDir;
	}

	function formatSize(bytes: number): string {
		if (bytes === 0) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB', 'TB'];
		const i = Math.floor(Math.log(bytes) / Math.log(1024));
		return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
	}

	function isDiscStructureDir(name: string): boolean {
		const upper = name.toUpperCase();
		return upper === 'BDMV' || upper === 'VIDEO_TS' || upper === 'CERTIFICATE' || upper === 'AUDIO_TS';
	}

	/** True if the current listing contains BDMV or VIDEO_TS - this folder IS a disc. */
	let currentIsDisc = $derived(
		entries.some((e) => e.type === 'directory' && (e.name.toUpperCase() === 'BDMV' || e.name.toUpperCase() === 'VIDEO_TS'))
	);

	/** Badge for entries that are disc structure internals. */
	function discBadgeFor(name: string): string | null {
		const upper = name.toUpperCase();
		if (upper === 'BDMV' || upper === 'CERTIFICATE') return 'Blu-ray';
		if (upper === 'VIDEO_TS' || upper === 'AUDIO_TS') return 'DVD';
		return null;
	}

	async function loadDirectory(path: string) {
		loading = true;
		error = null;
		filter = '';
		try {
			const listing = await fetchIngressDirectory(path);
			currentPath = path;
			entries = listing.entries;
			scrollContainer?.scrollTo(0, 0);
		} catch (e) {
			const msg = e instanceof Error ? e.message : 'Failed to load directory';
			error = msg.includes('unreachable') || msg.includes('503')
				? 'ARM service is starting up - try again in a moment'
				: msg;
		} finally {
			loading = false;
		}
	}

	function handleSelect(entry: DecoratedEntry) {
		if (!entry.importable) return;
		const fullPath = currentPath ? `${currentPath}/${entry.name}` : entry.name;
		selectedPath = fullPath;
		const kind: 'dir' | 'iso' = entry.kind === 'iso' ? 'iso' : 'dir';
		onselect({ path: fullPath, kind });
	}

	function handleOpen(entry: DecoratedEntry) {
		// Don't drill into disc structure internals or non-directory entries
		if (entry.kind !== 'dir') return;
		if (isDiscStructureDir(entry.name)) return;
		const fullPath = currentPath ? `${currentPath}/${entry.name}` : entry.name;
		selectedPath = null;
		loadDirectory(fullPath);
	}

	// When we navigate into a disc folder, auto-select the current path
	$effect(() => {
		if (currentIsDisc && currentPath) {
			selectedPath = currentPath;
			onselect({ path: currentPath, kind: 'dir' });
		}
	});

	function goBack() {
		if (!currentPath || currentPath === ingressPath) return;
		const parent = currentPath.replace(/\/[^/]+$/, '');
		if (!parent || !ingressPath || !parent.startsWith(ingressPath)) return;
		selectedPath = null;
		loadDirectory(parent);
	}

	async function init() {
		loading = true;
		error = null;
		needsConfig = false;
		try {
			const roots = await fetchIngressRoot();
			const ingress = roots.find((r) => r.key === 'ingress');
			if (!ingress) {
				needsConfig = true;
				loading = false;
				return;
			}
			ingressPath = ingress.path;
			await loadDirectory(ingress.path);
		} catch (e) {
			const msg = e instanceof Error ? e.message : 'Failed to load file roots';
			error = msg.includes('unreachable') || msg.includes('503')
				? 'ARM service is starting up - try again in a moment'
				: msg;
			loading = false;
		}
	}

	onMount(() => { init(); });
</script>

{#snippet sortIcon(key: string)}
	<SortIndicator dir={sortIconDir(key)} />
{/snippet}

<div class="flex min-h-0 flex-1 flex-col">
	{#if needsConfig}
		<div class="alert alert-warning alert-lg">
			<p class="alert-title">Folder Import Path is not configured</p>
			<p class="alert-body">Set the <strong>Folder Import Path</strong> in
				<button
					type="button"
					class="ingress-browser-config-link"
					onclick={() => { showImportWizard.set(false); goto('/settings#ripping/media-directories'); }}
				>Settings &rarr; Ripping &rarr; Media Directories</button>
				to the directory containing your BDMV/VIDEO_TS folders or ISO files.</p>
		</div>
	{:else if error}
		<div class="alert alert-danger alert-lg">
			<p>{error}</p>
			<button
				type="button"
				onclick={init}
				class="ingress-browser-retry"
			>Retry</button>
		</div>
	{:else if loading && entries.length === 0}
		<div class="ingress-browser-loading">Loading...</div>
	{:else}
		<!-- Navigation bar (pinned) -->
		<div class="shrink-0 stack stack-sm ingress-browser-nav">
			<!-- Path bar -->
			<div class="flex items-center gap-1 panel-section ingress-browser-path-bar">
				<svg class="h-4 w-4 shrink-0 ingress-browser-path-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
				</svg>
				<span class="truncate ingress-browser-path-text">{currentPath || ingressPath}</span>
			</div>
			{#if !currentIsDisc}
				<p class="ingress-browser-hint">Navigate to a folder containing BDMV or VIDEO_TS, or pick an ISO file.</p>
			{/if}

			<!-- Filter -->
			<input
				type="text"
				bind:value={filter}
				disabled={!filterEnabled}
				placeholder="Filter entries..."
				class="field-control"
			/>

			<!-- Disc detected banner -->
			{#if currentIsDisc}
				<div class="alert alert-success ingress-browser-disc-alert">
					Disc folder detected - this folder is ready to import.
				</div>
			{/if}
		</div>

		<!-- Directory table (scrollable) -->
		<div bind:this={scrollContainer} class="min-h-0 flex-1 overflow-y-auto ingress-browser-table-scroll" data-loading={loading}>
			<div class="ingress-browser-table-wrap">
				<table class="table ingress-browser-table">
					<colgroup>
						<col />
						<col class="w-20" />
						<col class="w-28" />
					</colgroup>
					<thead>
						<tr>
							<th class="table-header">
								<button type="button" onclick={() => toggleSort('name')} class="ingress-browser-sort-btn">Name {@render sortIcon('name')}</button>
							</th>
							<th class="table-header">
								<button type="button" onclick={() => toggleSort('size')} class="ingress-browser-sort-btn">Size {@render sortIcon('size')}</button>
							</th>
							<th class="table-header">
								<button type="button" onclick={() => toggleSort('modified')} class="ingress-browser-sort-btn">Modified {@render sortIcon('modified')}</button>
							</th>
						</tr>
					</thead>
					<tbody>
					{#if currentPath && currentPath !== ingressPath}
						<tr
							class="table-row ingress-browser-row"
							onclick={goBack}
						>
							<td class="table-cell">
								<div class="flex items-center gap-2">
									<svg class="h-4 w-4 shrink-0 ingress-browser-path-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 17l-5-5m0 0l5-5m-5 5h12" />
									</svg>
									<span class="ingress-browser-muted">..</span>
								</div>
							</td>
							<td class="table-cell"></td>
							<td class="table-cell"></td>
						</tr>
					{/if}
					{#if sortedEntries.length === 0}
						<tr><td colspan="3" class="table-cell ingress-browser-empty">No entries found.</td></tr>
					{/if}
						{#each sortedEntries as entry (entry.name)}
							{@const fullPath = currentPath ? `${currentPath}/${entry.name}` : entry.name}
							{@const isStructureDir = entry.kind === 'dir' && isDiscStructureDir(entry.name)}
							{@const badge = discBadgeFor(entry.name)}
							{@const disabled = !entry.importable || isStructureDir}
							<tr
								data-kind={entry.kind}
								data-disabled={disabled ? '' : undefined}
								aria-disabled={disabled ? 'true' : undefined}
								class="table-row ingress-browser-row"
								data-selected={!disabled && selectedPath === fullPath}
								onclick={() => { if (!disabled) handleSelect(entry); }}
								ondblclick={() => { if (!disabled) handleOpen(entry); }}
							>
								<td class="table-cell">
									<div class="flex items-center gap-2 overflow-hidden">
										<span class="shrink-0">
											{#if entry.kind === 'iso'}
												<Disc class="h-4 w-4 ingress-browser-icon-primary" />
											{:else if entry.kind === 'dir' && entry.importable && !isStructureDir}
												<FolderArchive class="h-4 w-4 ingress-browser-icon-primary" />
											{:else if entry.kind === 'dir'}
												<Folder class="h-4 w-4 ingress-browser-icon-muted" />
											{:else}
												<FileIcon class="h-4 w-4 ingress-browser-icon-faint" />
											{/if}
										</span>
										<span class="truncate ingress-browser-name" data-disabled={disabled}>{entry.name}</span>
										{#if badge}
											<span class="ingress-browser-disc-badge">
												{badge}
											</span>
										{/if}
									</div>
								</td>
								<td class="table-cell ingress-browser-muted">{formatSize(entry.size ?? 0)}</td>
								<td class="table-cell whitespace-nowrap ingress-browser-muted">
									{entry.modified ? new Date(entry.modified).toLocaleDateString() : '--'}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	{/if}
</div>

<style>
	.ingress-browser-config-link { text-decoration: underline; }
	/* the original was a soft danger pill (bg-red-100 text-red-800), not a
	   solid badge fill - no shared block matches this shape exactly */
	.ingress-browser-retry { margin-top: 0.5rem; border: 0; border-radius: var(--radius-md); padding: 0.25rem 0.75rem; font-size: 0.75rem; line-height: 1rem; font-weight: 500; cursor: pointer; background: var(--color-danger-soft); color: var(--color-on-danger-soft); }
	/* original was p-3 (0.75rem all sides), not .alert's own 0.5rem/0.75rem default */
	.ingress-browser-disc-alert { padding: 0.75rem; }
	.ingress-browser-retry:hover { background: color-mix(in srgb, var(--color-danger-soft) 60%, var(--color-danger)); }
	.ingress-browser-loading { padding: 2rem 0; text-align: center; color: var(--color-text-faint); }
	.ingress-browser-nav { padding-bottom: 0.5rem; }
	.ingress-browser-path-bar { font-size: 0.875rem; line-height: 1.25rem; padding: 0.375rem 0.75rem; }
	.ingress-browser-path-icon { color: var(--color-text-faint); }
	.ingress-browser-path-text { color: var(--color-text-secondary); }
	.ingress-browser-hint { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.ingress-browser-table-scroll { transition: opacity var(--motion-fast) var(--ease); }
	.ingress-browser-table-scroll[data-loading="true"] { pointer-events: none; opacity: 0.5; }
	.ingress-browser-table-wrap { border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
	.ingress-browser-table { table-layout: fixed; }
	.ingress-browser-sort-btn { color: inherit; }
	.ingress-browser-sort-btn:hover { color: var(--color-text-secondary); }
	.ingress-browser-row { cursor: pointer; }
	.ingress-browser-row[data-disabled] { cursor: default; opacity: 0.5; }
	.ingress-browser-muted { color: var(--color-text-muted); }
	.ingress-browser-empty { padding: 1.5rem 1rem; text-align: center; color: var(--color-text-faint); }
	/* :global: forwarded through lucide-svelte's Disc/FolderArchive class prop */
	:global(.ingress-browser-icon-primary) { color: var(--color-primary); }
	/* :global: forwarded through lucide-svelte's Folder class prop */
	:global(.ingress-browser-icon-muted) { color: var(--color-text-muted); }
	/* :global: forwarded through lucide-svelte's FileIcon class prop */
	:global(.ingress-browser-icon-faint) { color: var(--color-text-faint); }
	.ingress-browser-name { color: var(--color-text); }
	.ingress-browser-name[data-disabled="true"] { color: var(--color-text-faint); }
	/* the original was a soft warning pill (bg-amber-100 text-amber-700
	   text-[10px]), not badge-warning's solid fill */
	.ingress-browser-disc-badge { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-size: 10px; font-weight: 600; background: var(--color-warning-soft); color: var(--color-on-warning-soft); }
</style>
