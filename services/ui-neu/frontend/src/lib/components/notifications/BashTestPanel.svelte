<script lang="ts">
	import { ChevronRight } from 'lucide-svelte';
	import type { EventTypeInfo, ScriptInput } from '$lib/api/channels';
	import type { ChannelTemplate } from '$lib/types/notifications';
	import { BashPreview } from '../../stores/notification-bash-preview.svelte';
	import { armContext, incompleteInput, isCustomized, runSummary } from '../../notifications/bash-results';

	let {
		config,
		templates,
		events,
		eventTypes = [],
		channelId = null,
		inputs = []
	}: {
		config: Record<string, unknown>;
		templates: Record<string, ChannelTemplate>;
		events: string[];
		eventTypes?: EventTypeInfo[];
		channelId?: string | null;
		inputs?: ScriptInput[];
	} = $props();

	let open = $state(false);
	let eventType = $state('');
	const bash = new BashPreview();
	let showAll = $state(false);

	// A missing required input is a form-completion hint, not a failure:
	// name the field the way the Inputs block labels it.
	const incomplete = $derived(incompleteInput(bash.preview?.error, inputs));

	const subscribed = $derived(eventTypes.filter((e) => events.includes(e.key)));
	$effect(() => {
		if (!subscribed.some((e) => e.key === eventType)) eventType = subscribed[0]?.key ?? '';
	});

	function request(run: boolean) {
		return {
			config: { type: 'bash', ...config } as never,
			event_type: eventType,
			template: templates[eventType] ?? null,
			channel_id: channelId,
			run
		};
	}

	$effect(() => {
		// Track the form state so the preview refreshes as the user types.
		void JSON.stringify([config, templates[eventType]]);
		bash.cancel();
		if (!open || !eventType) return;
		bash.schedule(() => request(false));
		return bash.cancel;
	});

	const runTest = () => bash.run(request(true));

	const contextRows = $derived(armContext(bash.preview?.env ?? {}));
	const visibleContext = $derived(showAll ? contextRows : contextRows.slice(0, 6));
</script>

<div class="bash-test-panel">
	<button type="button" class="panel-title bash-test-panel-toggle" aria-expanded={open} onclick={() => (open = !open)}>
		<ChevronRight class="chevron" />
		Test
		{#if bash.lastRun}
			<span class="bash-test-panel-last-run" data-ok={bash.lastRun.ok}
				>last run: {bash.lastRun.ok ? 'passed' : 'failed'}</span
			>
		{/if}
	</button>
	{#if open}
		<div class="stack stack-sm bash-test-panel-body">
			<div class="bash-test-panel-row">
				<label class="field">
					<span class="field-label">Simulate event</span>
					<select aria-label="Simulate event" bind:value={eventType}>
						{#each subscribed as e (e.key)}
							<option value={e.key}>{e.label}{isCustomized(templates[e.key]) ? ' (customized)' : ''}</option>
						{/each}
					</select>
				</label>
				<button
					type="button"
					disabled={bash.running || !eventType || !!bash.preview?.error}
					onclick={runTest}
					class="btn btn-primary">{bash.running ? 'Running...' : 'Run test'}</button
				>
			</div>
			<p class="field-help">
				Runs the script now with sample values for the chosen event, using the form as it is, including unsaved changes.
			</p>

			{#if incomplete}
				<p class="alert alert-warning">Fill in {incomplete} above to preview this hook.</p>
			{:else if bash.preview?.error}
				<p class="alert alert-danger">{bash.preview.error}</p>
			{:else if bash.preview}
				<div class="bash-test-panel-grid">
					<div class="eyebrow bash-test-panel-grid-title">What the script will receive</div>
					<dl class="bash-test-panel-dl">
						<dt class="mono">$1</dt>
						<dd class="truncate">{bash.preview.title}</dd>
						<dt class="mono">$2</dt>
						<dd class="truncate">{bash.preview.body}</dd>
						{#if Object.keys(bash.preview.inputs).length}
							<dt class="eyebrow bash-test-panel-dl-heading">Inputs</dt>
							{#each Object.entries(bash.preview.inputs) as [k, v] (k)}
								<dt class="mono">{k}</dt>
								<dd class="truncate">{v}</dd>
							{/each}
						{/if}
						<dt class="eyebrow bash-test-panel-dl-heading">Context</dt>
						{#each visibleContext as [k, v] (k)}
							<dt class="mono">{k}</dt>
							<dd class="truncate">{v}</dd>
						{/each}
						{#if contextRows.length > 6}
							<dt></dt>
							<dd>
								<button type="button" class="btn btn-link" onclick={() => (showAll = !showAll)}
									>{showAll ? 'Show fewer' : `Show all ${contextRows.length}`}</button
								>
							</dd>
						{/if}
					</dl>
				</div>
			{/if}

			{#if bash.lastRun}
				<div class="alert bash-test-panel-result {bash.lastRun.ok ? 'alert-success' : 'alert-danger'}">
					<div class="bash-test-panel-result-grid">
						<span class="bash-test-panel-result-label">Result</span>
						<span>{runSummary(bash.lastRun)}</span>
						<span class="bash-test-panel-result-label">stderr</span>
						<pre class="code-block bash-test-panel-pre">{bash.lastRun.stderr || '(empty)'}</pre>
						<span class="bash-test-panel-result-label">stdout</span>
						<pre class="code-block bash-test-panel-pre">{bash.lastRun.stdout || '(empty)'}</pre>
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	/* Same look as .panel-section (border/radius/tint background) but the
	   padding lives on the toggle button and body separately, matching the
	   px-4 py-3 / px-4 pb-4 split rather than one uniform pad. */
	.bash-test-panel {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-primary-tint-1);
	}
	.bash-test-panel-toggle {
		margin-bottom: 0;
		padding: 0.75rem 1rem;
	}
	.bash-test-panel-last-run {
		margin-left: auto;
		font-weight: 400;
		text-transform: none;
		letter-spacing: normal;
		color: var(--color-status-error);
	}
	.bash-test-panel-last-run[data-ok='true'] {
		color: var(--color-success);
	}
	.bash-test-panel-body {
		padding: 0 1rem 1rem;
	}
	.bash-test-panel-row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: end;
		gap: 0.75rem;
	}
	/* the receive grid: a bordered box with a header row and a dt/dd table of
	   argv/inputs/context values. No block covers this shape. */
	.bash-test-panel-grid {
		overflow: hidden;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
	}
	.bash-test-panel-grid-title {
		border-bottom: 1px solid var(--color-border);
		padding: 0.5rem 0.75rem;
		color: var(--color-text-faint);
	}
	.bash-test-panel-dl {
		display: grid;
		grid-template-columns: max-content 1fr;
		column-gap: 1rem;
		row-gap: 0.25rem;
		padding: 0.5rem 0.75rem;
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.bash-test-panel-dl dt.mono {
		color: var(--color-primary-text);
	}
	.bash-test-panel-dl-heading {
		grid-column: span 2;
		margin-top: 0.5rem;
		color: var(--color-text-faint);
	}
	.bash-test-panel-result-grid {
		display: grid;
		grid-template-columns: max-content 1fr;
		column-gap: 0.75rem;
		row-gap: 0.25rem;
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.bash-test-panel-result-label {
		font-weight: 600;
	}
	/* the pre is plain (no box), inheriting the alert's own text-xs
	   size/line-height rather than code-block's 0.72rem/1.6. */
	.bash-test-panel-pre {
		margin: 0;
		border: 0;
		background: none;
		padding: 0;
		font-size: 0.75rem;
		line-height: 1rem;
		white-space: pre-wrap;
	}
</style>
