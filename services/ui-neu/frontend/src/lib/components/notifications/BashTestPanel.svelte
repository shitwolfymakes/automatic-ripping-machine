<script lang="ts">
	import { ChevronRight } from 'lucide-svelte';
	import { previewBash, type BashPreviewResult, type EventTypeInfo } from '$lib/api/channels';
	import { FIELD_INPUT_CLASS } from '$lib/types/notifications';
	import type { ChannelTemplate } from '$lib/types/notifications';

	let {
		config,
		templates,
		events,
		eventTypes = [],
		channelId = null
	}: { config: Record<string, unknown>; templates: Record<string, ChannelTemplate>; events: string[]; eventTypes?: EventTypeInfo[]; channelId?: string | null } = $props();

	let open = $state(false);
	let eventType = $state('');
	let preview = $state<BashPreviewResult | null>(null);
	let running = $state(false);
	let showAll = $state(false);
	let lastRun = $state<BashPreviewResult['result'] | null>(null);

	const subscribed = $derived(eventTypes.filter((e) => events.includes(e.key)));
	$effect(() => {
		if (!subscribed.some((e) => e.key === eventType)) eventType = subscribed[0]?.key ?? '';
	});

	function customized(key: string): boolean {
		const t = templates[key];
		return !!t && (!!t.title || !!t.body || !!(t.inputs && Object.keys(t.inputs).length));
	}

	function request(run: boolean) {
		return {
			config: { type: 'bash', ...config } as never,
			event_type: eventType,
			template: templates[eventType] ?? null,
			channel_id: channelId,
			run
		};
	}

	let timer: ReturnType<typeof setTimeout> | undefined;
	$effect(() => {
		// Track the form state so the preview refreshes as the user types.
		void JSON.stringify([config, templates[eventType]]);
		if (!open || !eventType) return;
		clearTimeout(timer);
		timer = setTimeout(async () => {
			try {
				preview = await previewBash(request(false));
			} catch (e) {
				preview = { title: '', body: '', inputs: {}, env: {}, argv: [], error: e instanceof Error ? e.message : 'preview failed', result: null };
			}
		}, 300);
		return () => clearTimeout(timer);
	});

	async function runTest() {
		running = true;
		try {
			const res = await previewBash(request(true));
			preview = res;
			lastRun = res.result ?? null;
		} catch (e) {
			lastRun = { ok: false, exit_code: null, duration_ms: 0, stdout: '', stderr: '', error: e instanceof Error ? e.message : 'test failed' };
		} finally {
			running = false;
		}
	}

	const contextRows = $derived(Object.entries(preview?.env ?? {}).filter(([k]) => k.startsWith('ARM_')));
	const visibleContext = $derived(showAll ? contextRows : contextRows.slice(0, 6));
</script>

<div class="rounded-lg border border-primary/15 bg-page dark:border-primary/20 dark:bg-primary/5">
	<button type="button" class="flex w-full items-center gap-2 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-primary" aria-expanded={open} onclick={() => (open = !open)}>
		<ChevronRight class="h-3.5 w-3.5 transition-transform {open ? 'rotate-90' : ''}" />
		Test
		{#if lastRun}
			<span class="ml-auto font-normal normal-case tracking-normal {lastRun.ok ? 'text-green-600 dark:text-green-400' : 'text-status-error'}">last run: {lastRun.ok ? 'passed' : 'failed'}</span>
		{/if}
	</button>
	{#if open}
		<div class="space-y-3 px-4 pb-4">
			<div class="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-3">
				<label class="flex flex-col gap-1">
					<span class="text-sm font-medium text-gray-700 dark:text-gray-300">Simulate event</span>
					<select aria-label="Simulate event" bind:value={eventType} class={FIELD_INPUT_CLASS}>
						{#each subscribed as e (e.key)}
							<option value={e.key}>{e.label}{customized(e.key) ? ' (customized)' : ''}</option>
						{/each}
					</select>
				</label>
				<button type="button" disabled={running || !eventType} onclick={runTest} class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:opacity-40">{running ? 'Running...' : 'Run test'}</button>
			</div>
			<p class="text-xs text-gray-500 dark:text-gray-400">Runs the script now with sample values for the chosen event, using the form as it is, including unsaved changes.</p>

			{#if preview?.error}
				<p class="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-900/20 dark:text-red-300">{preview.error}</p>
			{:else if preview}
				<div class="overflow-hidden rounded-md border border-primary/15 dark:border-primary/20">
					<div class="border-b border-primary/15 px-3 py-2 text-[11px] uppercase tracking-[0.08em] text-gray-400 dark:border-primary/20">What the script will receive</div>
					<dl class="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 px-3 py-2 text-xs">
						<dt class="font-mono text-primary-text dark:text-primary-text-dark">$1</dt><dd class="truncate">{preview.title}</dd>
						<dt class="font-mono text-primary-text dark:text-primary-text-dark">$2</dt><dd class="truncate">{preview.body}</dd>
						{#if Object.keys(preview.inputs).length}
							<dt class="col-span-2 mt-2 text-[11px] uppercase tracking-[0.08em] text-gray-400">Inputs</dt>
							{#each Object.entries(preview.inputs) as [k, v] (k)}
								<dt class="font-mono text-primary-text dark:text-primary-text-dark">{k}</dt><dd class="truncate">{v}</dd>
							{/each}
						{/if}
						<dt class="col-span-2 mt-2 text-[11px] uppercase tracking-[0.08em] text-gray-400">Context</dt>
						{#each visibleContext as [k, v] (k)}
							<dt class="font-mono text-primary-text dark:text-primary-text-dark">{k}</dt><dd class="truncate">{v}</dd>
						{/each}
						{#if contextRows.length > 6}
							<dt></dt><dd><button type="button" class="text-primary-text hover:underline dark:text-primary-text-dark" onclick={() => (showAll = !showAll)}>{showAll ? 'Show fewer' : `Show all ${contextRows.length}`}</button></dd>
						{/if}
					</dl>
				</div>
			{/if}

			{#if lastRun}
				<div class="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 rounded-md border px-3 py-2 text-xs {lastRun.ok ? 'border-green-300 bg-green-50 text-green-700 dark:border-green-500/40 dark:bg-green-900/20 dark:text-green-300' : 'border-red-300 bg-red-50 text-red-700 dark:border-red-500/40 dark:bg-red-900/20 dark:text-red-300'}">
					<span class="font-semibold">Result</span>
					<span>{lastRun.ok ? 'Passed' : 'Failed'}{lastRun.exit_code !== null ? `: exit code ${lastRun.exit_code}` : ''} after {(lastRun.duration_ms / 1000).toFixed(1)}s{!lastRun.ok && lastRun.exit_code === null && lastRun.error ? `: ${lastRun.error}` : ''}</span>
					<span class="font-semibold">stderr</span><pre class="whitespace-pre-wrap font-mono">{lastRun.stderr || '(empty)'}</pre>
					<span class="font-semibold">stdout</span><pre class="whitespace-pre-wrap font-mono">{lastRun.stdout || '(empty)'}</pre>
				</div>
			{/if}
		</div>
	{/if}
</div>
