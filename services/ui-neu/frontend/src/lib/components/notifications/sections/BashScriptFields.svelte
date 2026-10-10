<script lang="ts">
	import { onMount } from 'svelte';
	import { ChevronRight } from 'lucide-svelte';
	import { fetchScript, fetchScripts, type BashScriptInfo, type BashScriptSummary } from '$lib/api/channels';
	import SchemaField from '../SchemaField.svelte';
	import type { CatalogField } from '$lib/types/notifications';

	let {
		config = $bindable(),
		preserveExisting = false,
		onscript
	}: { config: Record<string, unknown>; preserveExisting?: boolean; onscript?: (info: BashScriptInfo | null) => void } = $props();

	let scripts = $state<BashScriptSummary[]>([]);
	let loaded = $state(false);
	let loadError = $state('');
	let info = $state<BashScriptInfo | null>(null);
	let infoMissing = $state(false);
	let viewerOpen = $state(false);

	const current = $derived(typeof config.script === 'string' ? config.script : '');
	const inputs = $derived((config.inputs as Record<string, string> | undefined) ?? {});

	async function loadList() {
		loaded = false;
		loadError = '';
		try {
			scripts = await fetchScripts();
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not list scripts';
		} finally {
			loaded = true;
		}
	}

	async function loadInfo(name: string) {
		info = null;
		infoMissing = false;
		if (!name) { onscript?.(null); return; }
		try {
			info = await fetchScript(name);
		} catch {
			infoMissing = true;
		}
		onscript?.(info);
	}

	onMount(() => {
		if (config.timeout_seconds === undefined) config.timeout_seconds = 30;
		if (config.inputs === undefined) config.inputs = {};
		void loadList();
		void loadInfo(current);
	});

	// Options: known scripts, plus the stored name when it is no longer on disk.
	const options = $derived.by(() => {
		const rows = scripts.map((s) => ({ ...s, missing: false }));
		if (current && !scripts.some((s) => s.name === current)) rows.unshift({ name: current, executable: false, description: '', missing: true });
		return rows;
	});

	function pick(name: string) {
		config.script = name;
		config.inputs = {};
		void loadInfo(name);
	}

	function fieldFor(i: NonNullable<BashScriptInfo['inputs']>[number]): CatalogField {
		return {
			key: i.key,
			label: i.label,
			type: i.values && i.values.length ? 'choice' : 'string',
			private: Boolean(i.secret),
			required: preserveExisting ? false : Boolean(i.required),
			default: i.default,
			values: i.values ?? undefined
		};
	}

	function setInput(key: string, value: unknown) {
		config.inputs = { ...inputs, [key]: value === undefined || value === null ? '' : String(value) };
	}
</script>

<div class="bash-script-fields-grid">
	<label class="field">
		<span class="field-label">Script *</span>
		<select aria-label="Script" value={current} onchange={(e) => pick((e.currentTarget as HTMLSelectElement).value)} required disabled={!loaded}>
			<option value="">{loaded ? (scripts.length ? 'Choose a script' : 'No scripts found') : 'Loading scripts...'}</option>
			{#each options as s (s.name)}
				<option value={s.name} disabled={!s.executable && !s.missing}>
					{s.name}{s.missing ? ' (missing)' : s.executable ? '' : ' (not executable)'}
				</option>
			{/each}
		</select>
	</label>
	<label class="field">
		<span class="field-label">Timeout (s)</span>
		<input type="number" aria-label="Timeout (seconds)" min="1" max="600" step="1" bind:value={config.timeout_seconds} />
	</label>
</div>

<div class="cluster bash-script-fields-refresh">
	{#if info?.description}<span>{info.description}</span>{/if}
	<span class="bash-script-fields-refresh-spacer"></span>
	<button type="button" class="btn btn-link bash-script-fields-refresh-btn" onclick={() => void loadList()}>Refresh list</button>
</div>

{#if loadError}
	<p class="bash-script-fields-status-error mt-3">{loadError}</p>
{:else if loaded && scripts.length === 0 && !current}
	<p class="field-help mt-3">
		No scripts found. Put an executable file in <code class="mono">arm/scripts/</code> on the host (<code class="mono">chmod +x</code>), then choose Refresh list.
	</p>
{/if}

{#if info}
	<div class="mt-3">
		<button type="button" class="btn btn-link btn-sm bash-script-fields-viewer-btn" aria-expanded={viewerOpen} onclick={() => (viewerOpen = !viewerOpen)}>
			<ChevronRight class="chevron" />
			View script
			<span class="bash-script-fields-viewer-meta">{info.name}, {info.size_bytes} B{info.executable ? '' : ', not executable'}</span>
		</button>
		{#if viewerOpen}
			<pre class="code-block code-block-scroll bash-script-fields-preview mt-2">{info.preview}</pre>
		{/if}
	</div>

	{#if info.inputs.length}
		<div class="bash-script-fields-inputs">
			<p class="bash-script-fields-inputs-title">Inputs <span class="bash-script-fields-inputs-note">(defaults for every event; each event can override non-secret inputs below)</span></p>
			{#if preserveExisting}
				<p class="field-help mb-3">Secret inputs show as hidden. Leave them as they are to keep the stored value.</p>
			{/if}
			<div class="grid-2">
				{#each info.inputs as i (i.key)}
					<SchemaField field={fieldFor(i)} value={inputs[i.key] ?? i.default} onchange={(v) => setInput(i.key, v)} />
				{/each}
			</div>
			<p class="field-help mt-3">Values may use the same variables as title and body, for example <code class="mono">{'{job_title}'}</code>.</p>
		</div>
	{:else}
		<p class="field-help mt-3">This script declares no inputs. Add <code class="mono"># arm-input:</code> lines to its header to get fields here.</p>
	{/if}
{:else if infoMissing}
	<p class="bash-script-fields-status-error mt-3">{current} is not in arm/scripts/ any more. Pick another script or restore the file.</p>
{/if}

<p class="field-help mt-3">
	Runs inside the arm-backend container as <code class="mono">bash script "title" "body"</code> with <code class="mono">ARM_*</code> variables and one variable per input. The script can reach the network and the media and raw mounts; it cannot run host commands.
</p>

<style>
	.bash-script-fields-grid { display: grid; grid-template-columns: 1fr; gap: 1rem; }
	@media (min-width: 640px) { .bash-script-fields-grid { grid-template-columns: 1fr 9rem; } }
	.bash-script-fields-refresh { margin-top: 0.5rem; gap: 0.75rem; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	/* .btn-link inherits .btn's own 0.875rem/1.25rem rather than this row's
	   text-xs (0.75rem/1rem); the original had no size class of its own,
	   inheriting the paragraph's text-xs (fix round 1). */
	.bash-script-fields-refresh-btn { font-size: 0.75rem; line-height: 1rem; }
	/* btn-sm sets font-size but not line-height (inherits .btn's 1.25rem);
	   the original was text-xs (1rem bundled line-height). */
	.bash-script-fields-viewer-btn { line-height: 1rem; }
	.bash-script-fields-refresh-spacer { margin-left: auto; }
	.bash-script-fields-viewer-meta { font-weight: 400; color: var(--color-text-muted); }
	/* the viewer is capped to keep the form scannable; nothing else uses this height */
	.bash-script-fields-preview { max-height: 14rem; font-size: 11.5px; line-height: 1.625; }
	.bash-script-fields-inputs { margin-top: 1rem; border-top: 1px solid var(--color-border); padding-top: 0.75rem; }
	.bash-script-fields-inputs-title { margin-bottom: 0.75rem; font-size: 0.75rem; line-height: 1rem; font-weight: 600; color: var(--color-text-secondary); }
	.bash-script-fields-inputs-note { font-weight: 400; color: var(--color-text-muted); }
	/* text-status-error (not field-error's --color-danger) matches the
	   original's status token; size restated since field-error's size isn't used here. */
	.bash-script-fields-status-error { font-size: 0.75rem; line-height: 1rem; color: var(--color-status-error); }
	/* field-help's own "code" descendant rule gives inline code a background
	   pill; the original's monospace code snippets here were always plain
	   text with no box, so that pill is switched off for this file's codes. */
	.field-help code.mono { padding: 0; border-radius: 0; background: none; }
</style>
