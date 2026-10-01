<script lang="ts">
	import { tick } from 'svelte';
	import { fetchIsoLibrary, startIsoRip } from '$lib/api/iso';
	import { fetchSessions } from '$lib/api/sessions';
	import { ApiError } from '$lib/api/client';
	import { addToast } from '$lib/stores/toast.svelte';
	import type { IsoLibraryEntry, IsoLibraryListing, SessionView } from '$lib/types/api.gen';
	import SlideOver from './SlideOver.svelte';
	import LoadState from './LoadState.svelte';
	import Glyph from './Glyph.svelte';

	interface Props {
		open: boolean;
		onclose: () => void;
		onstarted: (driveId: string) => void;
	}

	let { open, onclose, onstarted }: Props = $props();

	let subpath = $state('');
	let listing = $state<IsoLibraryListing | null>(null);
	let hostPath = $state('');
	let loading = $state(false);
	let notConfigured = $state(false);
	let loadError = $state<Error | null>(null);
	// Monotonic request counter: a load's own response is applied only if it
	// is still the most recently started one — an older, slower-resolving
	// request (e.g. a folder navigated away from) is discarded instead of
	// clobbering the newer listing.
	let loadSeq = 0;
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
	let activeIndex = $state(0);

	const rows = $derived(listing?.entries ?? []);
	const rowId = (index: number) => `iso-picker-row-${index}`;

	// The breadcrumb trail is derived from `subpath` alone (never from the
	// in-flight response) so it updates the instant a folder is opened, before
	// the fetch resolves — the loading skeleton then renders under the
	// destination folder's own breadcrumb, not the one being left.
	const breadcrumbItems = $derived.by(() => {
		const segments = subpath ? subpath.split('/') : [];
		const items: { label: string; path: string }[] = [{ label: 'Library', path: '' }];
		let acc = '';
		for (const seg of segments) {
			acc = acc ? `${acc}/${seg}` : seg;
			items.push({ label: seg, path: acc });
		}
		return items;
	});
	const currentLabel = $derived(breadcrumbItems[breadcrumbItems.length - 1].label);

	// Built from the server's own `listing.subpath`, not the optimistic
	// `subpath` state — the two can briefly disagree while a navigation is
	// in flight, and this is what decides the path sent to startIsoRip, so it
	// must always match whichever listing is actually on screen.
	function entryPath(name: string): string {
		const base = listing?.subpath ?? '';
		return base ? `${base}/${name}` : name;
	}

	function formatSize(bytes: number | null | undefined): string {
		if (bytes == null) return '--';
		if (bytes === 0) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB', 'TB'];
		const i = Math.floor(Math.log(bytes) / Math.log(1024));
		return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
	}

	function formatDate(modified: string | null | undefined): string {
		return modified ? new Date(modified).toLocaleDateString() : '--';
	}

	async function load(path: string): Promise<void> {
		subpath = path;
		loading = true;
		notConfigured = false;
		loadError = null;
		const seq = ++loadSeq;
		try {
			const result = await fetchIsoLibrary(path);
			if (seq !== loadSeq) return; // a newer navigation has since started; discard this stale response
			listing = result;
			hostPath = result.host_path;
			activeIndex = 0;
			// Clear loading BEFORE the refocus wait below, not in a trailing
			// `finally` — LoadState only mounts the ready rows once `loading`
			// goes false, so focusRow() would still find the skeleton (no row
			// with that id yet) if it ran first.
			loading = false;
			const shouldRefocus = loadedOnce;
			loadedOnce = true;
			if (shouldRefocus) {
				// The row that held focus just unmounted (LoadState swapped the
				// skeleton in while this load was pending) — bring focus back
				// into the list rather than stranding it on the body.
				await tick();
				focusRow(0);
			}
		} catch (e) {
			if (seq !== loadSeq) return;
			listing = null;
			loading = false;
			if (e instanceof ApiError && e.status === 503) {
				notConfigured = true;
			} else {
				loadError = e instanceof Error ? e : new Error('Could not load the library.');
			}
		}
	}

	function openFolder(name: string): void {
		load(entryPath(name));
	}

	function goTo(path: string): void {
		load(path);
	}

	function goUp(): void {
		if (listing?.parent_subpath != null) load(listing.parent_subpath);
	}

	function refresh(): void {
		load(subpath);
	}

	function isSelected(entry: IsoLibraryEntry): boolean {
		return entry.kind === 'iso' && selectedPath === entryPath(entry.name);
	}

	async function selectIso(entry: IsoLibraryEntry): Promise<void> {
		if (entry.ripping) return;
		selectedPath = entryPath(entry.name);
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
		activeIndex = index;
		if (entry.kind === 'folder') {
			openFolder(entry.name);
		} else {
			selectIso(entry);
		}
	}

	function focusRow(index: number): void {
		activeIndex = index;
		(document.getElementById(rowId(index)) as HTMLElement | null)?.focus();
	}

	function handleRowKeydown(e: KeyboardEvent, entry: IsoLibraryEntry, index: number): void {
		switch (e.key) {
			case 'ArrowDown':
				e.preventDefault();
				if (index < rows.length - 1) focusRow(index + 1);
				break;
			case 'ArrowUp':
				e.preventDefault();
				if (index > 0) focusRow(index - 1);
				break;
			case 'Home':
				e.preventDefault();
				if (rows.length > 0) focusRow(0);
				break;
			case 'End':
				e.preventDefault();
				if (rows.length > 0) focusRow(rows.length - 1);
				break;
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
				title: 'ISO rip started',
				body: `${selectedName} is in the ripping queue.`,
				link: { href: '/', label: 'View card' }
			});
			onstarted(created.drive_id);
		} catch (e) {
			startError = e instanceof Error ? e.message : 'Could not start the rip.';
		} finally {
			starting = false;
		}
	}

	function reset(): void {
		subpath = '';
		listing = null;
		hostPath = '';
		notConfigured = false;
		loadError = null;
		loadedOnce = false;
		sessionId = '';
		selectedPath = null;
		selectedName = null;
		startError = null;
		announcement = '';
		activeIndex = 0;
	}

	function handleClose(): void {
		onclose();
	}

	// Loads fresh every time the picker opens (never reuses stale state from a
	// previous open), and never fetches while closed — layouts that mount this
	// component unconditionally (e.g. for a guest-gating check elsewhere) must
	// not trigger a network call just by existing in the DOM.
	$effect(() => {
		if (open) {
			reset();
			load('');
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

<SlideOver {open} title="Rip from ISO" onclose={handleClose}>
	{#if notConfigured}
		<div class="alert alert-info iso-picker-setup">
			<p class="alert-title flex items-center gap-2">
				<Glyph name="info" />
				Set up your ISO library first
			</p>
			<div class="alert-body stack stack-sm">
				<p>ARM reads ISO files from one folder on the server. It doesn't know which folder yet.</p>
				<ol class="stack stack-sm iso-picker-setup-steps">
					<li>
						Point <code class="mono">ARM_HOST_ISO_LIBRARY_PATH</code> at the folder that holds your ISO files, for
						example a share on your NAS.
						<pre class="code-block iso-picker-setup-code">ARM_HOST_ISO_LIBRARY_PATH=/mnt/nas/iso</pre>
					</li>
					<li>
						Redeploy with <code class="mono">bash devtools/setup-dev.sh up</code> so the container can see the folder.
					</li>
					<li>Open Rip from ISO again and pick a file.</li>
				</ol>
				<p>ARM only reads this folder. It never moves, renames or deletes your ISO files.</p>
			</div>
		</div>
	{:else}
		<div class="stack">
			<div class="flex items-center justify-between">
				<h3 class="field-label">ISO file</h3>
				<button type="button" class="btn btn-icon" onclick={refresh} title="Refresh" aria-label="Refresh">
					<Glyph name="refresh" />
				</button>
			</div>

			<nav class="iso-picker-breadcrumb" aria-label="Library">
				{#each breadcrumbItems as item, i (item.path)}
					{#if i > 0}
						<Glyph name="chevron-right" class="h-3 w-3 iso-picker-breadcrumb-sep" />
					{/if}
					{#if i === breadcrumbItems.length - 1}
						<span class="iso-picker-breadcrumb-current" aria-current="page">{item.label}</span>
					{:else}
						<button type="button" class="iso-picker-breadcrumb-link" onclick={() => goTo(item.path)}>
							{item.label}
						</button>
					{/if}
				{/each}
			</nav>

			<LoadState data={listing} {loading} error={loadError} minDelay={0} isEmpty={(d) => d.entries.length === 0}>
				{#snippet loadingSlot()}
					<div class="panel iso-picker-list iso-picker-skeleton" aria-hidden="true">
						{#each Array.from({ length: 5 }) as _, i (i)}
							<div class="list-row list-row-compact">
								<span class="skeleton skeleton-text iso-picker-skeleton-lead"></span>
								<span class="skeleton skeleton-text iso-picker-skeleton-main"></span>
							</div>
						{/each}
					</div>
				{/snippet}
				{#snippet empty()}
					<p class="iso-picker-empty">This folder has no ISO files or folders.</p>
				{/snippet}
				{#snippet errorSlot(err)}
					<div class="alert alert-danger iso-picker-error">
						<p class="alert-title flex items-center gap-2">
							<Glyph name="x-circle" />
							Couldn't load the library
						</p>
						<p class="alert-body">{err.message}</p>
						<button type="button" class="btn btn-sm iso-picker-retry" onclick={refresh}>Retry</button>
					</div>
				{/snippet}
				{#snippet ready(data)}
					<div class="panel iso-picker-list" role="listbox" aria-label="ISO library">
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
								tabindex={i === activeIndex ? 0 : -1}
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
								</div>
								{#if entry.kind === 'iso'}
									<div class="list-row-meta iso-picker-meta">
										<span>{formatSize(entry.size_bytes)}</span>
										<span>{formatDate(entry.modified_at)}</span>
									</div>
								{/if}
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
				<p class="mono">{hostPath}</p>
				{#if loading}
					<p class="field-help">Loading {currentLabel}...</p>
				{:else}
					<p class="field-help">Read-only. Only .iso files are listed.</p>
				{/if}
			</div>

			<label class="field">
				<span class="field-label">Session <span class="iso-picker-optional">(optional)</span></span>
				<select bind:value={sessionId}>
					<option value="">Automatic</option>
					{#each sessions as s (s.id)}
						<option value={s.id}>{s.name}</option>
					{/each}
				</select>
				<span class="field-help">Automatic picks a session the same way it does for a disc in a drive.</span>
			</label>

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

	<div class="iso-picker-footer">
		{#if notConfigured}
			<p class="iso-picker-footer-helper">Nothing to pick until the library is set up.</p>
			<div class="flex gap-2">
				<button type="button" class="btn" onclick={handleClose}>Close</button>
			</div>
		{:else}
			<p class="iso-picker-footer-helper">
				{selectedName ? `Selected: ${selectedName}` : 'Pick an ISO to start.'}
			</p>
			<div class="flex gap-2">
				<button type="button" class="btn" onclick={handleClose} disabled={starting}>Cancel</button>
				<button type="button" class="btn btn-primary" onclick={handleStart} disabled={!selectedPath || starting}>
					{starting ? 'Starting...' : 'Start rip'}
				</button>
			</div>
		{/if}
	</div>
</SlideOver>

<style>
	.iso-picker-breadcrumb {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.875rem;
		line-height: calc(1.25 / 0.875);
	}
	.iso-picker-breadcrumb-link {
		border: 0;
		background: none;
		padding: 0;
		cursor: pointer;
		color: var(--color-primary-text);
		text-decoration: underline;
	}
	.iso-picker-breadcrumb-current {
		font-weight: 600;
		color: var(--color-text);
	}
	/* :global: forwarded through Glyph's class prop */
	:global(.iso-picker-breadcrumb-sep) {
		color: var(--color-text-faint);
	}
	.iso-picker-list {
		padding: 0;
	}
	.iso-picker-retry {
		margin-top: 0.5rem;
	}
	.iso-picker-row {
		grid-template-columns: auto 1fr auto auto;
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
	.iso-picker-meta {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}
	.iso-picker-empty {
		padding: 1.5rem 1rem;
		text-align: center;
		color: var(--color-text-faint);
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
	.iso-picker-hostpath {
		font-size: 0.75rem;
		line-height: calc(1 / 0.75);
	}
	.iso-picker-optional {
		margin-left: 0.25rem;
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	.iso-picker-setup-code {
		margin-top: 0.5rem;
	}
	.iso-picker-setup-steps {
		padding-left: 1.25rem;
		list-style: decimal;
	}
	/* The slide-over's body (SlideOver.svelte's own markup) is the scrolling
	   container; pinning the footer to ITS bottom (rather than letting it
	   scroll away with the content) is this component's one deliberate
	   departure from the New-session slide-over pattern (spec 7.1). Negative
	   margins cancel that body's p-6 so the footer spans full-bleed. */
	.iso-picker-footer {
		position: sticky;
		bottom: -1.5rem;
		margin: 1rem -1.5rem -1.5rem;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		border-top: 1px solid var(--color-border);
		background: var(--color-surface);
		padding: 0.75rem 1.5rem;
	}
	.iso-picker-footer-helper {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	@media (max-width: 400px) {
		.iso-picker-footer {
			flex-direction: column;
			align-items: stretch;
		}
	}
</style>
