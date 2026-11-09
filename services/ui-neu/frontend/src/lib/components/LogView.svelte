<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import type { LogEntry } from '$lib/api/logs';
	import { logService, serviceLabel } from '$lib/utils/log-service';
	import {
		chipBackground,
		chipText,
		countLabel,
		entryTimeLabel,
		filterEntries,
		followLabel,
		formatCopyText,
		levelTone,
		matchLabel,
		type LogLevelFilter,
		type LogServiceFilter
	} from '$lib/utils/log-view';
	import { uiPrefs, setUiPref } from '$lib/stores/uiPrefs';
	import { ClipboardCopy } from '$lib/stores/clipboardCopy.svelte';
	import { FollowScroll } from '$lib/stores/followScroll.svelte';
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
		/** Running count of live lines received; drives the paused "N new
		 *  lines" count, which entries.length can't once a capped feed drops
		 *  old lines. Defaults to entries.length. */
		appended?: number;
	}

	let {
		entries,
		error = null,
		loading = false,
		search = false,
		maxHeightClass = 'max-h-96',
		header = undefined,
		collapsed = false,
		appended = undefined
	}: Props = $props();

	let serviceFilter = $state<LogServiceFilter>('all');
	let levelFilter = $state<LogLevelFilter>('all');
	let searchText = $state('');
	let matchCase = $state(false);
	const clip = new ClipboardCopy();
	let frameEl = $state<HTMLDivElement | null>(null);
	let viewEl = $state<HTMLDivElement | null>(null);
	const follow = new FollowScroll(() => viewEl);
	let searchEl = $state<HTMLInputElement | null>(null);

	const wrap = $derived($uiPrefs.logWrap);

	const SERVICE_FILTERS: { key: LogServiceFilter; label: string }[] = [
		{ key: 'all', label: 'All' },
		{ key: 'backend', label: 'Backend' },
		{ key: 'ripper', label: 'Ripper' },
		{ key: 'transcode', label: 'Transcode' }
	];

	const LEVEL_FILTERS: { key: LogLevelFilter; label: string }[] = [
		{ key: 'all', label: 'All' },
		{ key: 'error', label: 'Error' },
		{ key: 'warning', label: 'Warning' },
		{ key: 'info', label: 'Info' },
		{ key: 'debug', label: 'Debug' }
	];

	const filtered = $derived(
		filterEntries(entries, {
			service: serviceFilter,
			level: levelFilter,
			query: search ? searchText : '',
			matchCase
		})
	);

	function clearSearch(): void {
		searchText = '';
		searchEl?.focus();
	}

	function copyLines(): void {
		clip.copy(formatCopyText(filtered));
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

	// Tracks the line count, the filter, the bound view and following, and
	// hands them to follow.sync.
	$effect(() => {
		const total = appended ?? entries.length;
		void filtered.length;
		const view = viewEl;
		const following = follow.following;
		untrack(() => follow.sync(total, view, following));
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
						<span class="log-view-search-count" data-testid="job-log-search-count">{matchLabel(filtered.length)}</span>
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
					<span aria-live="polite">{clip.copied ? 'Copied' : 'Copy'}</span>
				</button>
			</div>
		</div>

		<div class="relative">
			<div
				bind:this={viewEl}
				onscroll={follow.onScroll}
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
							<span class="shrink-0 log-view-time">{entryTimeLabel(entry)}</span>
							<span
								class="shrink-0 log-view-chip"
								style:--chip-bg={chipBackground(svc)}
								style:--chip-text={chipText(svc)}
							>
								{serviceLabel(svc)}
							</span>
							<span class="log-view-line" data-tone={levelTone(entry.level)}>{entry.event}</span>
						</div>
					{/each}
				{/if}
			</div>
			{#if !follow.following}
				<button
					type="button"
					onclick={follow.jumpToLatest}
					data-testid="job-log-jump"
					class="btn btn-primary btn-sm log-view-jump"
				>
					Jump to latest
				</button>
			{/if}
		</div>

		<div class="log-view-status">
			<span data-testid="job-log-count">{countLabel(filtered.length, entries.length)}</span>
			<span aria-hidden="true">·</span>
			<span data-testid="job-log-follow">{followLabel(follow.following, follow.newWhilePaused)}</span>
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
