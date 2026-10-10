<script lang="ts">
	import { ChevronRight } from 'lucide-svelte';
	import { previewBash, type BashPreviewResult, type EventTypeInfo, type ScriptInput } from '$lib/api/channels';
	import type { ChannelTemplate } from '$lib/types/notifications';

	let {
		config,
		templates,
		events,
		eventTypes = [],
		channelId = null,
		inputs = []
	}: { config: Record<string, unknown>; templates: Record<string, ChannelTemplate>; events: string[]; eventTypes?: EventTypeInfo[]; channelId?: string | null; inputs?: ScriptInput[] } = $props();

	// A missing required input is a form-completion hint, not a failure:
	// name the field the way the Inputs block labels it.
	const incomplete = $derived.by(() => {
		const m = preview?.error?.match(/^input ([A-Z][A-Z0-9_]*) is required$/);
		if (!m) return null;
		return inputs.find((i) => i.key === m[1])?.label ?? m[1];
	});

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
		clearTimeout(timer);
		if (!open || !eventType) return;
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

<div class="bash-test-panel">
	<button type="button" class="panel-title bash-test-panel-toggle" aria-expanded={open} onclick={() => (open = !open)}>
		<ChevronRight class="chevron" />
		Test
		{#if lastRun}
			<span class="bash-test-panel-last-run" data-ok={lastRun.ok}>last run: {lastRun.ok ? 'passed' : 'failed'}</span>
		{/if}
	</button>
	{#if open}
		<div class="stack stack-sm bash-test-panel-body">
			<div class="bash-test-panel-row">
				<label class="field">
					<span class="field-label">Simulate event</span>
					<select aria-label="Simulate event" bind:value={eventType}>
						{#each subscribed as e (e.key)}
							<option value={e.key}>{e.label}{customized(e.key) ? ' (customized)' : ''}</option>
						{/each}
					</select>
				</label>
				<button type="button" disabled={running || !eventType || !!preview?.error} onclick={runTest} class="btn btn-primary">{running ? 'Running...' : 'Run test'}</button>
			</div>
			<p class="field-help">Runs the script now with sample values for the chosen event, using the form as it is, including unsaved changes.</p>

			{#if incomplete}
				<p class="alert alert-warning">Fill in {incomplete} above to preview this hook.</p>
			{:else if preview?.error}
				<p class="alert alert-danger">{preview.error}</p>
			{:else if preview}
				<div class="bash-test-panel-grid">
					<div class="eyebrow bash-test-panel-grid-title">What the script will receive</div>
					<dl class="bash-test-panel-dl">
						<dt class="mono">$1</dt><dd class="truncate">{preview.title}</dd>
						<dt class="mono">$2</dt><dd class="truncate">{preview.body}</dd>
						{#if Object.keys(preview.inputs).length}
							<dt class="eyebrow bash-test-panel-dl-heading">Inputs</dt>
							{#each Object.entries(preview.inputs) as [k, v] (k)}
								<dt class="mono">{k}</dt><dd class="truncate">{v}</dd>
							{/each}
						{/if}
						<dt class="eyebrow bash-test-panel-dl-heading">Context</dt>
						{#each visibleContext as [k, v] (k)}
							<dt class="mono">{k}</dt><dd class="truncate">{v}</dd>
						{/each}
						{#if contextRows.length > 6}
							<dt></dt><dd><button type="button" class="btn btn-link" onclick={() => (showAll = !showAll)}>{showAll ? 'Show fewer' : `Show all ${contextRows.length}`}</button></dd>
						{/if}
					</dl>
				</div>
			{/if}

			{#if lastRun}
				<div class="alert bash-test-panel-result {lastRun.ok ? 'alert-success' : 'alert-danger'}">
					<div class="bash-test-panel-result-grid">
						<span class="bash-test-panel-result-label">Result</span>
						<span>{lastRun.ok ? 'Passed' : 'Failed'}{lastRun.exit_code !== null ? `: exit code ${lastRun.exit_code}` : ''} after {(lastRun.duration_ms / 1000).toFixed(1)}s{!lastRun.ok && lastRun.exit_code === null && lastRun.error ? `: ${lastRun.error}` : ''}</span>
						<span class="bash-test-panel-result-label">stderr</span><pre class="code-block bash-test-panel-pre">{lastRun.stderr || '(empty)'}</pre>
						<span class="bash-test-panel-result-label">stdout</span><pre class="code-block bash-test-panel-pre">{lastRun.stdout || '(empty)'}</pre>
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	/* Same look as .panel-section (border/radius/tint background) but the
	   padding lives on the toggle button and body separately, matching the
	   original's own px-4 py-3 / px-4 pb-4 split rather than one uniform pad. */
	.bash-test-panel { border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-primary-tint-1); }
	.bash-test-panel-toggle { margin-bottom: 0; padding: 0.75rem 1rem; }
	.bash-test-panel-last-run { margin-left: auto; font-weight: 400; text-transform: none; letter-spacing: normal; color: var(--color-status-error); }
	.bash-test-panel-last-run[data-ok="true"] { color: var(--color-success); }
	.bash-test-panel-body { padding: 0 1rem 1rem; }
	.bash-test-panel-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: 0.75rem; }
	/* the receive grid: a bordered box with a header row and a dt/dd table of
	   argv/inputs/context values. No block covers this shape. */
	.bash-test-panel-grid { overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-md); }
	.bash-test-panel-grid-title { border-bottom: 1px solid var(--color-border); padding: 0.5rem 0.75rem; color: var(--color-text-faint); }
	.bash-test-panel-dl { display: grid; grid-template-columns: max-content 1fr; column-gap: 1rem; row-gap: 0.25rem; padding: 0.5rem 0.75rem; font-size: 0.75rem; line-height: 1rem; }
	.bash-test-panel-dl dt.mono { color: var(--color-primary-text); }
	.bash-test-panel-dl-heading { grid-column: span 2; margin-top: 0.5rem; color: var(--color-text-faint); }
	.bash-test-panel-result-grid { display: grid; grid-template-columns: max-content 1fr; column-gap: 0.75rem; row-gap: 0.25rem; font-size: 0.75rem; line-height: 1rem; }
	.bash-test-panel-result-label { font-weight: 600; }
	/* the original pre was plain (no box), inheriting the alert's own text-xs
	   size/line-height rather than code-block's 0.72rem/1.6. */
	.bash-test-panel-pre { margin: 0; border: 0; background: none; padding: 0; font-size: 0.75rem; line-height: 1rem; white-space: pre-wrap; }
</style>
