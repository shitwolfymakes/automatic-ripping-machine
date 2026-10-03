<script lang="ts">
	import { onMount } from 'svelte';
	import { ChevronRight } from 'lucide-svelte';
	import { fetchScript, fetchScripts, type BashScriptInfo, type BashScriptSummary } from '$lib/api/channels';
	import { FIELD_INPUT_CLASS } from '$lib/types/notifications';
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

<div class="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_9rem]">
	<label class="flex flex-col gap-1">
		<span class="text-sm font-medium text-gray-700 dark:text-gray-300">Script *</span>
		<select aria-label="Script" value={current} onchange={(e) => pick((e.currentTarget as HTMLSelectElement).value)} required class={FIELD_INPUT_CLASS} disabled={!loaded}>
			<option value="">{loaded ? (scripts.length ? 'Choose a script' : 'No scripts found') : 'Loading scripts...'}</option>
			{#each options as s (s.name)}
				<option value={s.name} disabled={!s.executable && !s.missing}>
					{s.name}{s.missing ? ' (missing)' : s.executable ? '' : ' (not executable)'}
				</option>
			{/each}
		</select>
	</label>
	<label class="flex flex-col gap-1">
		<span class="text-sm font-medium text-gray-700 dark:text-gray-300">Timeout (s)</span>
		<input type="number" aria-label="Timeout (seconds)" min="1" max="600" step="1" bind:value={config.timeout_seconds} class={FIELD_INPUT_CLASS} />
	</label>
</div>

<div class="mt-2 flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
	{#if info?.description}<span>{info.description}</span>{/if}
	<span class="ml-auto"></span>
	<button type="button" class="text-primary-text hover:underline dark:text-primary-text-dark" onclick={() => void loadList()}>Refresh list</button>
</div>

{#if loadError}
	<p class="mt-3 text-xs text-status-error">{loadError}</p>
{:else if loaded && scripts.length === 0 && !current}
	<p class="mt-3 text-xs text-gray-500 dark:text-gray-400">
		No scripts found. Put an executable file in <code class="font-mono">arm/scripts/</code> on the host (<code class="font-mono">chmod +x</code>), then choose Refresh list.
	</p>
{/if}

{#if info}
	<div class="mt-3">
		<button type="button" class="flex items-center gap-1 text-xs font-semibold text-gray-700 dark:text-gray-300" aria-expanded={viewerOpen} onclick={() => (viewerOpen = !viewerOpen)}>
			<ChevronRight class="h-3.5 w-3.5 transition-transform {viewerOpen ? 'rotate-90' : ''}" />
			View script
			<span class="font-normal text-gray-500 dark:text-gray-400">{info.name}, {info.size_bytes} B{info.executable ? '' : ', not executable'}</span>
		</button>
		{#if viewerOpen}
			<pre class="mt-2 max-h-56 overflow-auto rounded-md border border-primary/15 bg-primary/5 p-3 font-mono text-[11.5px] leading-relaxed text-gray-800 dark:border-primary/20 dark:bg-primary/10 dark:text-gray-200">{info.preview}</pre>
		{/if}
	</div>

	{#if info.inputs.length}
		<div class="mt-4 border-t border-primary/15 pt-3 dark:border-primary/20">
			<p class="mb-3 text-xs font-semibold text-gray-700 dark:text-gray-300">Inputs <span class="font-normal text-gray-500 dark:text-gray-400">(defaults for every event; each event can override non-secret inputs below)</span></p>
			{#if preserveExisting}
				<p class="mb-3 text-xs text-gray-500 dark:text-gray-400">Secret inputs show as hidden. Leave them as they are to keep the stored value.</p>
			{/if}
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
				{#each info.inputs as i (i.key)}
					<SchemaField field={fieldFor(i)} value={inputs[i.key] ?? i.default} onchange={(v) => setInput(i.key, v)} />
				{/each}
			</div>
			<p class="mt-3 text-xs text-gray-500 dark:text-gray-400">Values may use the same variables as title and body, for example <code class="font-mono">{'{job_title}'}</code>.</p>
		</div>
	{:else}
		<p class="mt-3 text-xs text-gray-500 dark:text-gray-400">This script declares no inputs. Add <code class="font-mono"># arm-input:</code> lines to its header to get fields here.</p>
	{/if}
{:else if infoMissing}
	<p class="mt-3 text-xs text-status-error">{current} is not in arm/scripts/ any more. Pick another script or restore the file.</p>
{/if}

<p class="mt-3 text-xs text-gray-500 dark:text-gray-400">
	Runs inside the arm-backend container as <code class="font-mono">bash script "title" "body"</code> with <code class="font-mono">ARM_*</code> variables and one variable per input. The script can reach the network and the media and raw mounts; it cannot run host commands.
</p>
