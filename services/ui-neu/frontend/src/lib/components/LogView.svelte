<script lang="ts">
	import type { LogEntry } from '$lib/api/logs';
	import { logService, serviceLabel, type LogService } from '$lib/utils/log-service';

	interface Props {
		entries: LogEntry[];
		loading?: boolean;
		error?: Error | null;
		live?: boolean;
		search?: boolean;
		maxHeightClass?: string;
	}

	let {
		entries,
		loading = false,
		error = null,
		live = false,
		search = false,
		maxHeightClass = 'max-h-96'
	}: Props = $props();

	type Level = 'all' | 'error' | 'warning' | 'info' | 'debug';

	let serviceFilter = $state<'all' | LogService>('all');
	let levelFilter = $state<Level>('all');
	let searchText = $state('');
	let following = $state(true);
	let viewEl = $state<HTMLDivElement | null>(null);

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
		const needle = searchText.toLowerCase();
		return `${entry.event ?? ''} ${entry.logger ?? ''}`.toLowerCase().includes(needle);
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

	// Backend/ripper/transcode have no four-tone match; ripper takes the
	// warning tone (closest to the original's amber), transcode has no tone
	// at all so it takes an accent token (accent-3 violet, matching the
	// Series video-type hue's precedent for an untoned axis), backend keeps
	// the primary-tinted default the "info-ish" original already used.
	function chipVar(service: LogService): string {
		switch (service) {
			case 'backend':
				return 'var(--color-primary-tint-3)';
			case 'ripper':
				return 'var(--color-warning-soft)';
			case 'transcode':
				return 'color-mix(in srgb, var(--color-accent-3) 15%, transparent)';
			default:
				return 'var(--color-primary-tint-2)';
		}
	}

	function chipTextVar(service: LogService): string {
		switch (service) {
			case 'backend':
				return 'var(--color-primary-text)';
			case 'ripper':
				return 'var(--color-on-warning-soft)';
			case 'transcode':
				return 'var(--color-accent-3)';
			default:
				return 'var(--color-text-secondary)';
		}
	}

	function levelTone(level: string): 'warning' | 'danger' | null {
		switch ((level ?? '').toLowerCase()) {
			case 'warning':
				return 'warning';
			case 'error':
			case 'critical':
				return 'danger';
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

	$effect(() => {
		// Follow new lines (filtered.length as the reactive trigger) while
		// the user hasn't scrolled up.
		void filtered.length;
		if (following) scrollToBottom();
	});
</script>

<div class="flex flex-col gap-3">
	<div class="flex flex-wrap items-center gap-2">
		<div class="log-view-segment-group" role="radiogroup" aria-label="Log filter">
			{#each SERVICE_FILTERS as f}
				<button
					type="button"
					role="radio"
					aria-checked={serviceFilter === f.key}
					data-testid="job-log-filter-{f.key}"
					onclick={() => {
						serviceFilter = f.key;
					}}
					class="log-view-segment"
				>{f.label}</button>
			{/each}
		</div>
		<div class="log-view-segment-group" role="radiogroup" aria-label="Log level filter">
			{#each LEVEL_FILTERS as f}
				<button
					type="button"
					role="radio"
					aria-checked={levelFilter === f.key}
					data-testid="job-log-level-{f.key}"
					onclick={() => {
						levelFilter = f.key;
					}}
					class="log-view-segment"
				>{f.label}</button>
			{/each}
		</div>
		{#if search}
			<input
				type="text"
				bind:value={searchText}
				placeholder="Filter lines"
				data-testid="job-log-search"
				class="ml-auto field-control log-view-search"
			/>
		{/if}
	</div>

	{#if isFiltered}
		<p data-testid="job-log-count" class="field-help">
			Showing {filtered.length} of {entries.length} lines
		</p>
	{/if}

	{#if error}
		<p class="log-view-message" data-tone="error">{error.message}</p>
	{:else if entries.length === 0}
		<p class="log-view-message">No log lines for this job yet.</p>
	{:else}
		<div class="relative">
			<div
				bind:this={viewEl}
				onscroll={onScroll}
				data-testid="job-log-view"
				class="{maxHeightClass} log-view-terminal"
			>
				{#each filtered as entry, i (i)}
					{@const svc = logService(entry.service)}
					<div class="flex items-start gap-2 py-0.5" data-testid="job-log-line" data-service={svc}>
						<span class="shrink-0 log-view-time mono">{timeLabel(entry)}</span>
						<span class="shrink-0 log-view-chip" style:--chip-bg={chipVar(svc)} style:--chip-text={chipTextVar(svc)}>
							{serviceLabel(svc)}
						</span>
						<span class="break-all log-view-line" data-tone={levelTone(entry.level)}>{entry.event}</span>
					</div>
				{/each}
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
	{/if}
</div>

<style>
	.log-view-segment-group { display: flex; gap: 0.25rem; border-radius: var(--radius-lg); background: var(--color-primary-tint-1); padding: 0.25rem; }
	.log-view-segment { border-radius: var(--radius-md); padding: 0.375rem 0.75rem; font-size: 0.75rem; line-height: 1rem; font-weight: 500; color: var(--color-text-secondary); background: transparent; transition: background-color var(--motion-fast) var(--ease), color var(--motion-fast) var(--ease); }
	.log-view-segment:hover { background: var(--color-primary-tint-2); }
	.log-view-segment[aria-checked="true"] { background: var(--color-primary); color: var(--color-on-primary); }
	.log-view-search { width: auto; }
	.log-view-message { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.log-view-message[data-tone="error"] { color: var(--color-danger); }
	/* the original terminal background was an unqualified bg-black/90 (same
	   in both modes); --color-on-frame-accent is the only mode-independent
	   pure-black token, composed here via color-mix for the 90% opacity */
	.log-view-terminal { overflow-y: auto; border-radius: var(--radius-lg); border: 1px solid var(--color-border); background: color-mix(in srgb, var(--color-on-frame-accent) 90%, transparent); padding: 0.75rem; font-family: var(--font-mono); font-size: 0.75rem; line-height: 1rem; }
	/* the terminal surface is fixed near-black in both modes (see
	   .log-view-terminal above); its text must stay a fixed light shade too,
	   not the theme-flipping --color-text-* roles - --color-on-primary is
	   the only mode-independent pure-white token, composed via color-mix for
	   each line's original grayscale/tone shade */
	.log-view-time { color: color-mix(in srgb, var(--color-on-primary) 62%, transparent); }
	/* Tailwind's arbitrary text-[10px] still carries its own default
	   line-height ratio (1.3333, i.e. 4/3 - not the ancestor's inherited
	   1rem/16px); dropping the utility silently lost that, shrinking the
	   chip (and with it every log row's height) by a few px per row. */
	.log-view-chip { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-size: 10px; line-height: 1.3333333333333333; font-weight: 600; background: var(--chip-bg); color: var(--chip-text); }
	.log-view-line { color: color-mix(in srgb, var(--color-on-primary) 82%, transparent); }
	.log-view-line[data-tone="warning"] { color: var(--color-warning); }
	.log-view-line[data-tone="danger"] { color: var(--color-danger); }
	.log-view-jump { position: absolute; bottom: 0.75rem; right: 0.75rem; box-shadow: var(--shadow-2); }
</style>
