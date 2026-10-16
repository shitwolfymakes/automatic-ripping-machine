<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import type { LogEntry } from '$lib/api/logs';
	import { logService, serviceLabel, type LogService } from '$lib/utils/log-service';
	import { uiPrefs, setUiPref } from '$lib/stores/uiPrefs';
	import CloseButton from '$lib/components/CloseButton.svelte';

	interface Props {
		entries: LogEntry[];
		error?: Error | null;
		/** First fetch pending: a loading line replaces the empty state. */
		loading?: boolean;
		search?: boolean;
		maxHeightClass?: string;
		/** Title-bar content (toggle, counts, links), rendered inside the frame. */
		header?: Snippet;
		/** When true only the title bar renders. */
		collapsed?: boolean;
	}

	let {
		entries,
		error = null,
		loading = false,
		search = false,
		maxHeightClass = 'max-h-96',
		header = undefined,
		collapsed = false
	}: Props = $props();

	type Level = 'all' | 'error' | 'warning' | 'info' | 'debug';
	type Tone = 'warning' | 'danger' | 'debug' | null;

	let serviceFilter = $state<'all' | LogService>('all');
	let levelFilter = $state<Level>('all');
	let searchText = $state('');
	let matchCase = $state(false);
	let following = $state(true);
	let newWhilePaused = $state(0);
	let copied = $state(false);
	let frameEl = $state<HTMLDivElement | null>(null);
	let viewEl = $state<HTMLDivElement | null>(null);
	let searchEl = $state<HTMLInputElement | null>(null);
	let copyTimer: ReturnType<typeof setTimeout> | null = null;

	const wrap = $derived($uiPrefs.logWrap);

	const SERVICE_FILTERS: { key: 'all' | LogService; label: string }[] = [
		{ key: 'all', label: 'All' },
		{ key: 'backend', label: 'Backend' },
		{ key: 'ripper', label: 'Ripper' },
		{ key: 'transcode', label: 'Transcode' }
	];

	const LEVEL_FILTERS: { key: Level; label: string }[] = [
		{ key: 'all', label: 'All' },
		{ key: 'error', label: 'Error' },
		{ key: 'warning', label: 'Warning' },
		{ key: 'info', label: 'Info' },
		{ key: 'debug', label: 'Debug' }
	];

	function levelOf(entry: LogEntry): string {
		return (entry.level ?? '').toLowerCase();
	}

	function matchesSearch(entry: LogEntry): boolean {
		if (!search || !searchText) return true;
		const hay = `${entry.event ?? ''} ${entry.logger ?? ''}`;
		return matchCase ? hay.includes(searchText) : hay.toLowerCase().includes(searchText.toLowerCase());
	}

	const filtered = $derived(
		entries.filter((e) => {
			if (serviceFilter !== 'all' && logService(e.service) !== serviceFilter) return false;
			if (levelFilter !== 'all' && levelOf(e) !== levelFilter) return false;
			if (!matchesSearch(e)) return false;
			return true;
		})
	);

	const isFiltered = $derived(filtered.length !== entries.length);

	const countLabel = $derived(
		isFiltered ? `Showing ${filtered.length} of ${entries.length} lines` : `${entries.length} lines`
	);

	const matchLabel = $derived(`${filtered.length} ${filtered.length === 1 ? 'match' : 'matches'}`);

	const followLabel = $derived(
		following
			? 'Following'
			: newWhilePaused === 0
				? 'Paused'
				: `Paused · ${newWhilePaused} new ${newWhilePaused === 1 ? 'line' : 'lines'}`
	);

	// The well is a fixed dark surface in both modes (see the --color-terminal-*
	// tokens), so the chips take fixed-dark recipes mixed towards the ink rather
	// than the mode-flipping tone tokens. Backend tints from primary, ripper
	// from accent-1 (amber) and transcode from accent-3 (violet).
	function chipVar(service: LogService): string {
		switch (service) {
			case 'backend':
				return 'color-mix(in srgb, var(--color-primary) 26%, transparent)';
			case 'ripper':
				return 'color-mix(in srgb, var(--color-accent-1) 28%, transparent)';
			case 'transcode':
				return 'color-mix(in srgb, var(--color-accent-3) 22%, transparent)';
			default:
				return 'color-mix(in srgb, var(--color-terminal-ink) 10%, transparent)';
		}
	}

	function chipTextVar(service: LogService): string {
		switch (service) {
			case 'backend':
				return 'color-mix(in srgb, var(--color-primary) 45%, var(--color-terminal-ink))';
			case 'ripper':
				return 'color-mix(in srgb, var(--color-accent-1) 60%, var(--color-terminal-ink))';
			case 'transcode':
				return 'color-mix(in srgb, var(--color-accent-3) 45%, var(--color-terminal-ink))';
			default:
				return 'color-mix(in srgb, var(--color-terminal-ink) 70%, transparent)';
		}
	}

	function levelTone(level: string): Tone {
		switch ((level ?? '').toLowerCase()) {
			case 'warning':
				return 'warning';
			case 'error':
			case 'critical':
				return 'danger';
			case 'debug':
				return 'debug';
			default:
				return null;
		}
	}

	function timeLabel(entry: LogEntry): string {
		if (!entry.timestamp) return '';
		const d = new Date(entry.timestamp);
		if (Number.isNaN(d.getTime())) return '';
		return d.toLocaleTimeString([], { hour12: false });
	}

	function isAtBottom(): boolean {
		if (viewEl === null) return true;
		return viewEl.scrollHeight - viewEl.scrollTop - viewEl.clientHeight < 24;
	}

	function onScroll(): void {
		following = isAtBottom();
	}

	function jumpToLatest(): void {
		following = true;
		scrollToBottom();
	}

	function scrollToBottom(): void {
		if (viewEl === null) return;
		viewEl.scrollTop = viewEl.scrollHeight;
	}

	function clearSearch(): void {
		searchText = '';
		searchEl?.focus();
	}

	function copyLines(): void {
		const text = filtered
			.map((e) => `${timeLabel(e)} [${serviceLabel(logService(e.service))}] ${e.event ?? ''}`)
			.join('\n');
		const clipboard = typeof navigator === 'undefined' ? undefined : navigator.clipboard;
		if (!clipboard) return;
		clipboard
			.writeText(text)
			.then(() => {
				copied = true;
				if (copyTimer) clearTimeout(copyTimer);
				copyTimer = setTimeout(() => (copied = false), 1500);
			})
			.catch(() => {
				/* no clipboard access (http, permissions): the label just stays "Copy" */
			});
	}

	// "/" focuses the search while focus is somewhere inside the frame and not
	// already in a text field. Listened on the window (rather than the frame
	// div) so the frame stays a plain, non-interactive container.
	function onWindowKeydown(e: KeyboardEvent): void {
		if (e.key !== '/' || !search || collapsed || searchEl === null || frameEl === null) return;
		const target = e.target as HTMLElement | null;
		if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return;
		if (!frameEl.contains(document.activeElement)) return;
		e.preventDefault();
		searchEl.focus();
	}

	// Follow new lines while the user hasn't scrolled up; while paused, count
	// the lines that arrived so the status bar can say how many are waiting.
	let seen = 0;
	$effect(() => {
		const total = entries.length;
		void filtered.length;
		const follow = following;
		untrack(() => {
			if (follow) {
				newWhilePaused = 0;
				scrollToBottom();
			} else if (total > seen) {
				newWhilePaused += total - seen;
			}
			seen = total;
		});
	});
</script>

<svelte:window onkeydown={onWindowKeydown} />

<!-- One dark, primary-tinted terminal window: title bar, toolbar, lines and
     status bar all sit on the same well (design handoff option 1b). -->
<div class="log-view-frame" data-testid="log-view" data-collapsed={collapsed || undefined} bind:this={frameEl}>
	{#if header}
		<div class="log-view-titlebar" data-testid="log-view-titlebar">
			{@render header()}
		</div>
	{/if}

	{#if !collapsed}
		<div class="log-view-toolbar">
			<div class="log-view-segment-group" role="radiogroup" aria-label="Log filter">
				{#each SERVICE_FILTERS as f (f.key)}
					<button
						type="button"
						role="radio"
						aria-checked={serviceFilter === f.key}
						data-testid="job-log-filter-{f.key}"
						onclick={() => {
							serviceFilter = f.key;
						}}
						class="log-view-segment">{f.label}</button
					>
				{/each}
			</div>
			<span class="log-view-divider" aria-hidden="true"></span>
			<div class="log-view-segment-group" role="radiogroup" aria-label="Log level filter">
				{#each LEVEL_FILTERS as f (f.key)}
					<button
						type="button"
						role="radio"
						aria-checked={levelFilter === f.key}
						data-testid="job-log-level-{f.key}"
						onclick={() => {
							levelFilter = f.key;
						}}
						class="log-view-segment">{f.label}</button
					>
				{/each}
			</div>
			{#if search}
				<div class="log-view-search">
					<span class="log-view-search-prompt" aria-hidden="true">/</span>
					<input
						type="text"
						bind:value={searchText}
						bind:this={searchEl}
						placeholder="Filter lines"
						aria-label="Filter lines"
						data-testid="job-log-search"
					/>
					{#if searchText}
						<span class="log-view-search-count" data-testid="job-log-search-count">{matchLabel}</span>
						<CloseButton label="Clear filter" class="log-view-search-clear" onclick={clearSearch} />
					{/if}
					<button
						type="button"
						class="log-view-search-case"
						aria-pressed={matchCase}
						aria-label="Match case"
						title="Match case"
						data-testid="job-log-search-case"
						onclick={() => {
							matchCase = !matchCase;
						}}>Aa</button
					>
				</div>
			{/if}
			<div class="log-view-tools">
				<button
					type="button"
					class="log-view-tool"
					aria-pressed={wrap}
					data-testid="job-log-wrap"
					onclick={() => setUiPref('logWrap', !wrap)}>Wrap</button
				>
				<button type="button" class="log-view-tool" data-testid="job-log-copy" onclick={copyLines}>
					<span aria-live="polite">{copied ? 'Copied' : 'Copy'}</span>
				</button>
			</div>
		</div>

		<div class="relative">
			<div
				bind:this={viewEl}
				onscroll={onScroll}
				data-testid="job-log-view"
				data-wrap={wrap}
				class="{maxHeightClass} log-view-terminal"
			>
				{#if loading}
					<p class="log-view-message">Loading log...</p>
				{:else if error}
					<p class="log-view-message" data-tone="error">{error.message}</p>
				{:else if entries.length === 0}
					<p class="log-view-message">No log lines for this job yet.</p>
				{:else}
					{#each filtered as entry, i (i)}
						{@const svc = logService(entry.service)}
						<div class="flex items-start gap-2 py-0.5" data-testid="job-log-line" data-service={svc}>
							<span class="shrink-0 log-view-time">{timeLabel(entry)}</span>
							<span class="shrink-0 log-view-chip" style:--chip-bg={chipVar(svc)} style:--chip-text={chipTextVar(svc)}>
								{serviceLabel(svc)}
							</span>
							<span class="log-view-line" data-tone={levelTone(entry.level)}>{entry.event}</span>
						</div>
					{/each}
				{/if}
			</div>
			{#if !following}
				<button
					type="button"
					onclick={jumpToLatest}
					data-testid="job-log-jump"
					class="btn btn-primary btn-sm log-view-jump"
				>
					Jump to latest
				</button>
			{/if}
		</div>

		<div class="log-view-status">
			<span data-testid="job-log-count">{countLabel}</span>
			<span aria-hidden="true">·</span>
			<span data-testid="job-log-follow">{followLabel}</span>
		</div>
	{/if}
</div>

<style>
	.log-view-frame {
		border-radius: var(--radius-lg);
		overflow: hidden;
		border: 1px solid color-mix(in srgb, var(--color-primary) 30%, transparent);
		background: var(--color-terminal-bg);
		color: var(--color-terminal-ink);
	}

	.log-view-titlebar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.625rem 0.875rem;
		background: color-mix(in srgb, var(--color-primary) 10%, transparent);
		border-bottom: 1px solid color-mix(in srgb, var(--color-primary) 22%, transparent);
	}
	.log-view-frame[data-collapsed='true'] .log-view-titlebar {
		border-bottom: 0;
	}
	/* the title bar's links (btn-link) are recoloured for the dark well */
	.log-view-titlebar :global(.btn-link) {
		font-size: 0.8125rem;
		color: color-mix(in srgb, var(--color-primary) 55%, var(--color-terminal-ink));
	}

	.log-view-toolbar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.75rem;
		padding: 0.5rem 0.875rem;
		border-bottom: 1px solid color-mix(in srgb, var(--color-terminal-ink) 6%, transparent);
	}
	.log-view-segment-group {
		display: flex;
		gap: 2px;
	}
	.log-view-divider {
		width: 1px;
		height: 18px;
		background: color-mix(in srgb, var(--color-terminal-ink) 12%, transparent);
	}
	.log-view-segment {
		border-radius: var(--radius-sm);
		padding: 0.25rem 0.5625rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		color: color-mix(in srgb, var(--color-terminal-ink) 65%, transparent);
		background: transparent;
		transition:
			background-color var(--motion-fast) var(--ease),
			color var(--motion-fast) var(--ease);
	}
	.log-view-segment:hover {
		background: color-mix(in srgb, var(--color-terminal-ink) 6%, transparent);
	}
	.log-view-segment[aria-checked='true'] {
		background: color-mix(in srgb, var(--color-primary) 32%, transparent);
		color: color-mix(in srgb, var(--color-primary) 40%, var(--color-terminal-ink));
	}

	/* search: a composite field that grows into the leftover toolbar space */
	.log-view-search {
		flex: 1 1 140px;
		min-width: 120px;
		height: 28px;
		box-sizing: border-box;
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 0 6px 0 9px;
		border-radius: var(--radius-sm);
		border: 1px solid color-mix(in srgb, var(--color-terminal-ink) 10%, transparent);
		background: color-mix(in srgb, var(--color-terminal-ink) 4%, transparent);
	}
	.log-view-search:focus-within {
		border-color: color-mix(in srgb, var(--color-primary) 50%, transparent);
	}
	.log-view-search-prompt {
		font: 0.75rem var(--font-mono);
		color: color-mix(in srgb, var(--color-terminal-ink) 45%, transparent);
	}
	.log-view-search input {
		flex: 1;
		min-width: 0;
		border: 0;
		background: transparent;
		outline: none;
		padding: 0;
		font: 0.75rem var(--font-mono);
		color: var(--color-terminal-ink);
	}
	.log-view-search input::placeholder {
		color: color-mix(in srgb, var(--color-terminal-ink) 40%, transparent);
	}
	.log-view-search-count {
		font: 0.6875rem var(--font-mono);
		color: color-mix(in srgb, var(--color-terminal-ink) 50%, transparent);
		white-space: nowrap;
	}
	/* the shared CloseButton, shrunk to sit inside the 28px field */
	.log-view-search :global(.log-view-search-clear) {
		min-height: auto;
		height: auto;
		width: auto;
		padding: 2px 3px;
		border: 0;
		background: none;
		font-size: 13px;
		color: color-mix(in srgb, var(--color-terminal-ink) 60%, transparent);
	}
	.log-view-search-case {
		font: 600 0.6875rem var(--font-mono);
		padding: 2px 5px;
		border-radius: 3px;
		color: color-mix(in srgb, var(--color-terminal-ink) 75%, transparent);
	}
	.log-view-search-case[aria-pressed='true'] {
		background: color-mix(in srgb, var(--color-primary) 32%, transparent);
	}

	.log-view-tools {
		display: flex;
		gap: 2px;
		margin-left: auto;
	}
	.log-view-tool {
		font-size: 0.75rem;
		line-height: 1rem;
		padding: 0.25rem 0.5625rem;
		border-radius: var(--radius-sm);
		color: color-mix(in srgb, var(--color-terminal-ink) 80%, transparent);
	}
	.log-view-tool:hover {
		background: color-mix(in srgb, var(--color-terminal-ink) 6%, transparent);
	}
	.log-view-tool[aria-pressed='true'] {
		background: color-mix(in srgb, var(--color-terminal-ink) 8%, transparent);
	}

	.log-view-terminal {
		overflow-y: auto;
		padding: 0.625rem 0.875rem;
		font-family: var(--font-mono);
		font-size: 0.75rem;
		line-height: 1.5;
	}
	.log-view-terminal[data-wrap='false'] {
		overflow-x: auto;
	}
	.log-view-message {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: color-mix(in srgb, var(--color-terminal-ink) 55%, transparent);
	}
	.log-view-message[data-tone='error'] {
		color: color-mix(in srgb, var(--color-danger) 75%, var(--color-terminal-ink));
	}
	.log-view-time {
		color: color-mix(in srgb, var(--color-terminal-ink) 45%, transparent);
	}
	.log-view-chip {
		border-radius: 3px;
		padding: 0 6px;
		font-size: 10px;
		line-height: 16px;
		font-weight: 600;
		background: var(--chip-bg);
		color: var(--chip-text);
	}
	.log-view-line {
		color: color-mix(in srgb, var(--color-terminal-ink) 86%, transparent);
	}
	.log-view-terminal[data-wrap='true'] .log-view-line {
		white-space: pre-wrap;
		word-break: break-all;
	}
	.log-view-terminal[data-wrap='false'] .log-view-line {
		white-space: pre;
	}
	.log-view-line[data-tone='debug'] {
		color: color-mix(in srgb, var(--color-terminal-ink) 50%, transparent);
	}
	.log-view-line[data-tone='warning'] {
		color: color-mix(in srgb, var(--color-warning) 80%, var(--color-terminal-ink));
	}
	.log-view-line[data-tone='danger'] {
		color: color-mix(in srgb, var(--color-danger) 75%, var(--color-terminal-ink));
	}

	.log-view-jump {
		position: absolute;
		bottom: 0.625rem;
		right: 0.875rem;
		border-radius: 9999px;
		box-shadow: var(--shadow-2);
	}

	.log-view-status {
		display: flex;
		flex-wrap: wrap;
		gap: 0.625rem;
		padding: 0.375rem 0.875rem;
		font: 0.6875rem var(--font-mono);
		color: color-mix(in srgb, var(--color-terminal-ink) 50%, transparent);
		border-top: 1px solid color-mix(in srgb, var(--color-terminal-ink) 6%, transparent);
	}
</style>
