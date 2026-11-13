<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import { tick } from 'svelte';
	import { startIsoRip } from '$lib/api/iso';
	import { fetchSessions } from '$lib/api/sessions';
	import { addToast } from '$lib/stores/toast.svelte';
	import { IsoLibraryBrowser } from '$lib/stores/iso-library-browser.svelte';
	import type { IsoFolderEntry, IsoLibraryEntry, SessionView } from '$lib/types/api.gen';
	import SlideOver from './SlideOver.svelte';
	import LoadState from './LoadState.svelte';
	import Glyph from './Glyph.svelte';
	import IsoLibrarySetup from './iso-picker/IsoLibrarySetup.svelte';
	import IsoPathBreadcrumb from './iso-picker/IsoPathBreadcrumb.svelte';
	import IsoPickerFooter from './iso-picker/IsoPickerFooter.svelte';
	import { pathTailTruncate } from '$lib/utils/truncate';
	import { formatBytes } from '$lib/utils/format';
	import { pathTrail } from '$lib/utils/path';
	import { isListboxNavKey, nextRowIndex } from '$lib/utils/listbox-nav';

	interface Props {
		open: boolean;
		/** `iso`: browse the library for an .iso file. `folder`: one flat list of
		 *  every disc folder (BDMV / VIDEO_TS) in the library, with a filter. */
		mode?: 'iso' | 'folder';
		onclose: () => void;
		onstarted: (driveId: string) => void;
	}

	let { open, mode = 'iso', onclose, onstarted }: Props = $props();

	const isFolderMode = $derived(mode === 'folder');
	const browser = new IsoLibraryBrowser();
	let filter = $state('');
	// Matches anywhere in the library path, so "rings" finds every disc of a set.
	const folderRows = $derived.by(() => {
		const needle = filter.trim().toLowerCase();
		const entries = browser.folderListing?.entries ?? [];
		return needle ? entries.filter((f) => f.path.toLowerCase().includes(needle)) : entries;
	});

	// False only for the very first load after the picker opens, so that
	// initial render never steals focus; every subsequent load (a folder
	// open, Up, or refresh) restores it to the first row once the new data
	// is in, since LoadState's skeleton swap unmounts whatever row held it.
	let loadedOnce = false;

	let sessions = $state<SessionView[]>([]);
	let sessionId = $state('');

	let selectedPath = $state<string | null>(null);
	let selectedName = $state<string | null>(null);

	let startError = $state<string | null>(null);
	let starting = $state(false);

	let announcement = $state('');

	const rows = $derived(browser.listing?.entries ?? []);
	const rowId = (index: number) => `iso-picker-row-${index}`;

	// The breadcrumb trail is derived from `subpath` alone (never from the
	// in-flight response) so it updates the instant a folder is opened, before
	// the fetch resolves — the loading skeleton then renders under the
	// destination folder's own breadcrumb, not the one being left.
	const breadcrumbItems = $derived([{ label: 'Library', path: '' }, ...pathTrail(browser.subpath)]);
	const currentLabel = $derived(breadcrumbItems[breadcrumbItems.length - 1].label);

	function formatSize(bytes: number | null | undefined): string {
		return bytes == null ? '--' : formatBytes(bytes);
	}

	function formatDate(modified: string | null | undefined): string {
		return modified ? new Date(modified).toLocaleDateString() : '--';
	}

	// Every load but the first after the picker opens puts focus back on the
	// first row once the rows are shown, because LoadState's skeleton swap
	// unmounts whatever row held it.
	async function browseTo(path: string): Promise<void> {
		if (!(await browser.loadLibrary(path))) return;
		const shouldRefocus = loadedOnce;
		loadedOnce = true;
		if (shouldRefocus) {
			// The row that held focus just unmounted (LoadState swapped the
			// skeleton in while this load was pending) — bring focus back
			// into the list rather than stranding it on the body.
			await tick();
			focusRow(0);
		}
	}

	function openFolder(name: string): void {
		browseTo(browser.entryPath(name));
	}

	function goUp(): void {
		if (browser.listing?.parent_subpath != null) browseTo(browser.listing.parent_subpath);
	}

	function isSelected(entry: IsoLibraryEntry): boolean {
		return entry.kind === 'iso' && selectedPath === browser.entryPath(entry.name);
	}

	async function selectIso(entry: IsoLibraryEntry): Promise<void> {
		if (entry.ripping) return;
		selectedPath = browser.entryPath(entry.name);
		selectedName = entry.name;
		startError = null;
		// Clear first: reassigning to identical wording is a DOM no-op for the
		// live region, so back-to-back selections of names/sizes that happen to
		// match would otherwise go unannounced (RankedListField precedent).
		announcement = '';
		await tick();
		announcement = `Selected ${entry.name}, ${formatSize(entry.size_bytes)}.`;
	}

	function activate(entry: IsoLibraryEntry, index: number): void {
		browser.activeIndex = index;
		if (entry.kind === 'folder') {
			openFolder(entry.name);
		} else {
			selectIso(entry);
		}
	}

	async function selectFolder(entry: IsoFolderEntry, index: number): Promise<void> {
		browser.activeIndex = index;
		if (entry.ripping) return;
		selectedPath = entry.path;
		selectedName = entry.name;
		startError = null;
		announcement = '';
		await tick();
		announcement = `Selected ${entry.path}.`;
	}

	function handleFolderKeydown(e: KeyboardEvent, entry: IsoFolderEntry, index: number): void {
		if (moveFocus(e, index, folderRows.length)) return;
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			selectFolder(entry, index);
		}
	}

	function discLabel(type: string): string {
		return type === 'bluray' ? 'BD' : 'DVD';
	}

	function focusRow(index: number): void {
		browser.activeIndex = index;
		(document.getElementById(rowId(index)) as HTMLElement | null)?.focus();
	}

	/** Moves focus for a navigation key; false when the key is not one. */
	function moveFocus(e: KeyboardEvent, index: number, count: number): boolean {
		if (!isListboxNavKey(e.key)) return false;
		e.preventDefault();
		const target = nextRowIndex(e.key, index, count);
		if (target !== null) focusRow(target);
		return true;
	}

	function handleRowKeydown(e: KeyboardEvent, entry: IsoLibraryEntry, index: number): void {
		if (moveFocus(e, index, rows.length)) return;
		switch (e.key) {
			case 'Enter':
			case ' ':
				e.preventDefault();
				activate(entry, index);
				break;
			case 'Backspace':
			case 'ArrowLeft':
				e.preventDefault();
				goUp();
				break;
		}
	}

	async function handleStart(): Promise<void> {
		if (!selectedPath || starting) return;
		starting = true;
		startError = null;
		try {
			const created = await startIsoRip(selectedPath, sessionId || null);
			addToast({
				tone: 'success',
				title: isFolderMode ? 'Folder rip started' : 'ISO rip started',
				body: `${selectedName} is in the ripping queue.`,
				link: { href: '/', label: 'View card' }
			});
			onstarted(created.drive_id);
		} catch (e) {
			startError = errorMessage(e, 'Could not start the rip.');
		} finally {
			starting = false;
		}
	}

	function reset(): void {
		browser.reset();
		filter = '';
		loadedOnce = false;
		sessionId = '';
		selectedPath = null;
		selectedName = null;
		startError = null;
		announcement = '';
	}

	// Loads fresh every time the picker opens (never reuses stale state from a
	// previous open), and never fetches while closed — layouts that mount this
	// component unconditionally (e.g. for a guest-gating check elsewhere) must
	// not trigger a network call just by existing in the DOM.
	$effect(() => {
		if (open) {
			reset();
			if (isFolderMode) {
				browser.loadFolders();
			} else {
				browseTo('');
			}
			fetchSessions()
				.then((s) => {
					sessions = s;
				})
				.catch(() => {
					sessions = [];
				});
		}
	});
</script>

<SlideOver {open} title={isFolderMode ? 'Rip from folder' : 'Rip from ISO'} {onclose}>
	<div class="iso-picker">
		<div class="iso-picker-main">
			{#if browser.notConfigured}
				<IsoLibrarySetup />
			{:else}
				<div class="stack">
					{#if isFolderMode}
						<section class="panel stack stack-sm iso-picker-panel" aria-labelledby="iso-picker-folder-title">
							<div class="iso-picker-panel-head">
								<h3 id="iso-picker-folder-title" class="panel-title iso-picker-panel-title">Disc folder</h3>
								<button
									type="button"
									class="btn btn-icon"
									onclick={() => browser.loadFolders()}
									title="Refresh"
									aria-label="Refresh"
								>
									<Glyph name="refresh" />
								</button>
							</div>

							<input
								type="search"
								class="input"
								placeholder="Filter by name or path"
								aria-label="Filter folders"
								bind:value={filter}
							/>

							<LoadState
								data={browser.folderListing}
								loading={browser.loading}
								error={browser.loadError}
								minDelay={0}
								isEmpty={(d) => d.entries.length === 0}
							>
								{#snippet loadingSlot()}
									<div class="iso-picker-list iso-picker-skeleton" aria-hidden="true">
										{#each Array.from({ length: 5 }) as _, i (i)}
											<div class="list-row list-row-compact">
												<span class="skeleton skeleton-text iso-picker-skeleton-lead"></span>
												<span class="skeleton skeleton-text iso-picker-skeleton-main"></span>
											</div>
										{/each}
									</div>
								{/snippet}
								{#snippet empty()}
									<div class="iso-picker-list iso-picker-empty">
										<Glyph name="folder" class="iso-picker-empty-icon" />
										<p class="iso-picker-empty-title">No disc folders in the library.</p>
										<p class="iso-picker-empty-hint">
											Copy a disc folder (one with BDMV or VIDEO_TS inside) into the library, then refresh.
										</p>
									</div>
								{/snippet}
								{#snippet errorSlot(err)}
									<div class="alert alert-danger iso-picker-error">
										<p class="alert-title flex items-center gap-2">
											<Glyph name="x-circle" />
											Couldn't load the library
										</p>
										<p class="alert-body">{err.message}</p>
										<button type="button" class="btn btn-sm iso-picker-retry" onclick={() => browser.loadFolders()}
											>Retry</button
										>
									</div>
								{/snippet}
								{#snippet ready(data)}
									{#if data.partial}
										<p class="iso-picker-hostpath-note">
											The library is very large, so ARM stopped searching partway. Some disc folders may be missing.
										</p>
									{/if}
									{#if folderRows.length === 0}
										<div class="iso-picker-list iso-picker-empty">
											<p class="iso-picker-empty-title">No folder matches "{filter}".</p>
										</div>
									{:else}
										<div class="iso-picker-list" role="listbox" aria-label="Disc folders">
											{#each folderRows as entry, i (entry.path)}
												{@const selected = selectedPath === entry.path}
												<div
													role="option"
													id={rowId(i)}
													class="list-row list-row-compact iso-picker-row"
													data-kind="disc-folder"
													aria-selected={selected}
													aria-disabled={entry.ripping || undefined}
													data-state={entry.ripping ? 'ripping' : undefined}
													aria-label={entry.name}
													tabindex={i === browser.activeIndex ? 0 : -1}
													onclick={() => selectFolder(entry, i)}
													onkeydown={(e) => handleFolderKeydown(e, entry, i)}
												>
													<div class="list-row-lead">
														<Glyph name="folder" class="iso-picker-icon-folder" />
													</div>
													<div class="list-row-main">
														<div class="iso-picker-row-name" data-selected={selected} title={entry.path}>
															{entry.name}
														</div>
														{#if entry.parent}
															<div class="iso-picker-row-detail iso-picker-row-parent" title={entry.path}>
																{pathTailTruncate(entry.parent, 48)}
															</div>
														{/if}
													</div>
													<div class="list-row-actions">
														<span class="chip chip-sm">{discLabel(entry.disc_type)}</span>
														{#if entry.ripping}
															<span class="chip chip-warning chip-sm">Ripping</span>
														{:else if selected}
															<Glyph name="check-circle" class="iso-picker-icon-selected" />
														{/if}
													</div>
												</div>
											{/each}
										</div>
									{/if}
								{/snippet}
							</LoadState>

							<div class="iso-picker-hostpath">
								<Glyph name="folder" class="iso-picker-hostpath-icon" />
								<div>
									<p class="mono iso-picker-hostpath-path">{browser.hostPath}</p>
									<p class="iso-picker-hostpath-note">
										{browser.loading
											? 'Searching the library...'
											: 'Read-only. Only folders with BDMV or VIDEO_TS are listed.'}
									</p>
								</div>
							</div>
						</section>
					{:else}
						<section class="panel stack stack-sm iso-picker-panel" aria-labelledby="iso-picker-file-title">
							<div class="iso-picker-panel-head">
								<h3 id="iso-picker-file-title" class="panel-title iso-picker-panel-title">ISO file</h3>
								<button
									type="button"
									class="btn btn-icon"
									onclick={() => browseTo(browser.subpath)}
									title="Refresh"
									aria-label="Refresh"
								>
									<Glyph name="refresh" />
								</button>
							</div>

							<IsoPathBreadcrumb items={breadcrumbItems} onnavigate={browseTo} />

							<LoadState
								data={browser.listing}
								loading={browser.loading}
								error={browser.loadError}
								minDelay={0}
								isEmpty={(d) => d.entries.length === 0}
							>
								{#snippet loadingSlot()}
									<div class="iso-picker-list iso-picker-skeleton" aria-hidden="true">
										{#each Array.from({ length: 5 }) as _, i (i)}
											<div class="list-row list-row-compact">
												<span class="skeleton skeleton-text iso-picker-skeleton-lead"></span>
												<span class="skeleton skeleton-text iso-picker-skeleton-main"></span>
											</div>
										{/each}
									</div>
								{/snippet}
								{#snippet empty()}
									<div class="iso-picker-list iso-picker-empty">
										<Glyph name="disc-3" class="iso-picker-empty-icon" />
										<p class="iso-picker-empty-title">This folder has no ISO files or folders.</p>
										<p class="iso-picker-empty-hint">Copy .iso files into the library on the server, then refresh.</p>
									</div>
								{/snippet}
								{#snippet errorSlot(err)}
									<div class="alert alert-danger iso-picker-error">
										<p class="alert-title flex items-center gap-2">
											<Glyph name="x-circle" />
											Couldn't load the library
										</p>
										<p class="alert-body">{err.message}</p>
										<button type="button" class="btn btn-sm iso-picker-retry" onclick={() => browseTo(browser.subpath)}
											>Retry</button
										>
									</div>
								{/snippet}
								{#snippet ready(data)}
									<div class="iso-picker-list" role="listbox" aria-label="ISO library">
										{#each data.entries as entry, i (entry.name)}
											{@const selected = isSelected(entry)}
											{@const disabled = entry.kind === 'iso' && entry.ripping}
											<div
												role="option"
												id={rowId(i)}
												class="list-row list-row-compact iso-picker-row"
												data-kind={entry.kind}
												aria-selected={selected}
												aria-disabled={disabled || undefined}
												data-state={disabled ? 'ripping' : undefined}
												aria-label={entry.name}
												tabindex={i === browser.activeIndex ? 0 : -1}
												onclick={() => activate(entry, i)}
												onkeydown={(e) => handleRowKeydown(e, entry, i)}
											>
												<div class="list-row-lead">
													{#if entry.kind === 'folder'}
														<Glyph name="folder" class="iso-picker-icon-folder" />
													{:else}
														<Glyph name="disc-3" class="iso-picker-icon-disc" />
													{/if}
												</div>
												<div class="list-row-main">
													<div class="iso-picker-row-name" data-selected={selected} title={entry.name}>
														{entry.name}
													</div>
													{#if entry.kind === 'iso'}
														<div class="iso-picker-row-detail">
															{formatSize(entry.size_bytes)} · {formatDate(entry.modified_at)}
														</div>
													{/if}
												</div>
												<div class="list-row-actions">
													{#if entry.kind === 'folder'}
														<Glyph name="chevron-right" />
													{:else if disabled}
														<span class="chip chip-warning chip-sm">Ripping</span>
													{:else if selected}
														<Glyph name="check-circle" class="iso-picker-icon-selected" />
													{/if}
												</div>
											</div>
										{/each}
									</div>
								{/snippet}
							</LoadState>

							<div class="iso-picker-hostpath">
								<Glyph name="folder" class="iso-picker-hostpath-icon" />
								<div>
									<p class="mono iso-picker-hostpath-path">{browser.hostPath}</p>
									{#if browser.loading}
										<p class="iso-picker-hostpath-note">Loading {currentLabel}...</p>
									{:else}
										<p class="iso-picker-hostpath-note">Read-only. Only .iso files are listed.</p>
									{/if}
								</div>
							</div>
						</section>
					{/if}

					<section class="panel stack stack-sm iso-picker-panel">
						<label class="field">
							<span class="panel-title iso-picker-panel-title">
								Session <span class="iso-picker-optional">optional</span>
							</span>
							<select bind:value={sessionId}>
								<option value="">Automatic</option>
								{#each sessions as s (s.id)}
									<option value={s.id}>{s.name}</option>
								{/each}
							</select>
							<span class="field-help">Automatic picks a session the same way it does for a disc in a drive.</span>
						</label>
					</section>

					{#if startError}
						<div class="alert alert-danger iso-picker-error">
							<p class="alert-title flex items-center gap-2">
								<Glyph name="x-circle" />
								Couldn't start the rip
							</p>
							<p class="alert-body">{startError}</p>
						</div>
					{/if}
				</div>
			{/if}

			<div class="sr-only" aria-live="polite">{announcement}</div>
		</div>

		<IsoPickerFooter
			notConfigured={browser.notConfigured}
			{isFolderMode}
			{selectedName}
			{selectedPath}
			{starting}
			{onclose}
			onstart={handleStart}
		/>
	</div>
</SlideOver>

<style>
	/* Each section is a site panel with an eyebrow title, as in Settings. */
	.iso-picker-panel-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}
	/* panel-title's own bottom margin is replaced by the panel's stack gap. */
	.iso-picker-panel-title {
		margin-bottom: 0;
	}
	/* The file list (and its loading and empty states) sits in one framed
	   box inside the panel, so the panel keeps the same shape in every state. */
	.iso-picker-list {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
		overflow: hidden;
	}
	/* The parent path is pre-shortened from the left (pathTailTruncate); this
	   only guards a very narrow panel. The full path is in the title. */
	.iso-picker-row-parent {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.iso-picker-retry {
		margin-top: 0.5rem;
	}
	.iso-picker-row {
		grid-template-columns: auto minmax(0, 1fr) auto;
	}
	.iso-picker-row[aria-disabled='true'] {
		/* Disabled per spec's own convention (opacity 0.4 + not-allowed), keyed
		   off aria-disabled rather than list-row.css's data-disabled — this row
		   stays focusable (roving tabindex still lands on it), just inert. */
		opacity: 0.4;
		cursor: not-allowed;
	}
	.iso-picker-row[aria-selected='true'] {
		box-shadow: inset 0 0 0 1px var(--color-primary);
	}
	.iso-picker-row-name[data-selected='true'] {
		font-weight: 700;
	}
	/* :global: forwarded through Glyph's class prop */
	:global(.iso-picker-icon-folder) {
		color: var(--color-text-muted);
	}
	/* :global: forwarded through Glyph's class prop */
	:global(.iso-picker-icon-disc) {
		color: var(--color-primary);
	}
	/* :global: forwarded through Glyph's class prop */
	:global(.iso-picker-icon-selected) {
		color: var(--color-primary);
	}
	.iso-picker-row-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	/* Size and date sit under the name, so a long file name gets the row's
	   full width instead of sharing it with a data column. */
	.iso-picker-row-detail {
		font-size: 0.75rem;
		line-height: calc(1 / 0.75);
		color: var(--color-text-muted);
	}
	.iso-picker-empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		padding: 2rem 1rem;
		text-align: center;
		background: var(--color-primary-tint-1);
	}
	/* :global: forwarded through Glyph's class prop */
	:global(.iso-picker-empty-icon) {
		width: 2rem;
		height: 2rem;
		margin-bottom: 0.25rem;
		color: var(--color-text-faint);
	}
	.iso-picker-empty-title {
		font-size: 0.875rem;
		line-height: calc(1.25 / 0.875);
		font-weight: 500;
		color: var(--color-text);
	}
	.iso-picker-empty-hint {
		font-size: 0.75rem;
		line-height: calc(1 / 0.75);
		color: var(--color-text-muted);
	}
	.iso-picker-skeleton {
		gap: 0;
	}
	.iso-picker-skeleton-lead {
		width: 1rem;
	}
	.iso-picker-skeleton-main {
		width: 60%;
	}
	/* The library path is the ISO file panel's bottom bar: full-bleed across
	   the panel (negative margins cancel .panel's 1rem padding), with the
	   panel's own bottom corners. */
	.iso-picker-hostpath {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		margin: 0.25rem -1rem -1rem;
		border-top: 1px solid var(--color-border);
		border-radius: 0 0 var(--radius-lg) var(--radius-lg);
		background: var(--color-primary-tint-1);
		padding: 0.625rem 1rem;
		font-size: 0.75rem;
		line-height: calc(1 / 0.75);
	}
	/* :global: forwarded through Glyph's class prop */
	:global(.iso-picker-hostpath-icon) {
		flex-shrink: 0;
		width: 1rem;
		height: 1rem;
		color: var(--color-text-faint);
	}
	.iso-picker-hostpath-path {
		color: var(--color-text);
		word-break: break-all;
	}
	.iso-picker-hostpath-note {
		color: var(--color-text-muted);
	}
	/* Sits inside the eyebrow title, so it drops the uppercase and tracking. */
	.iso-picker-optional {
		margin-left: 0.25rem;
		font-weight: 400;
		letter-spacing: normal;
		text-transform: none;
		color: var(--color-text-faint);
	}
	/* The picker fills SlideOver's scrolling body (min-height: 100% of its
	   content box) as a column, so the footer sits at the panel's bottom
	   even when the library is short or empty; sticky keeps it there when a
	   long list scrolls. */
	.iso-picker {
		display: flex;
		flex-direction: column;
		min-height: 100%;
	}
	.iso-picker-main {
		flex: 1 0 auto;
		padding-bottom: 1rem;
	}
</style>
