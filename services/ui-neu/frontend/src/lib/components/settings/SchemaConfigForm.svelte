<script lang="ts">
	import type { SettingsGroup, ConfigFieldMeta } from '$lib/types/api.gen';
	import { saveArmConfig } from '$lib/api/settings';
	import ConfigSchemaField from './ConfigSchemaField.svelte';

	let {
		group,
		config,
		onsaved
	}: {
		group: SettingsGroup;
		config: Record<string, unknown>;
		onsaved?: (payload: Record<string, unknown>) => void;
	} = $props();

	const HIDDEN = '<hidden>';
	const editable = $derived(group.fields.filter((f: ConfigFieldMeta) => f.editable));

	let values = $state<Record<string, unknown>>({});
	$effect(() => {
		const next: Record<string, unknown> = {};
		for (const f of group.fields) next[f.key] = config[f.key];
		values = next;
	});

	let saving = $state(false);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	function buildPayload(): Record<string, unknown> {
		const out: Record<string, unknown> = {};
		for (const f of editable) {
			const v = values[f.key];
			if (f.tier === 'secret' && (v === HIDDEN || v === '' || v == null)) continue;
			if (v === config[f.key]) continue;
			out[f.key] = v;
		}
		return out;
	}

	async function save() {
		saving = true;
		feedback = null;
		try {
			const payload = buildPayload();
			await saveArmConfig(payload as never);
			feedback = { type: 'success', message: 'Saved' };
			onsaved?.(payload);
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Save failed' };
		} finally {
			saving = false;
		}
	}
</script>

<section class="space-y-4">
	<h2 class="text-lg font-semibold text-gray-900 dark:text-white">{group.name}</h2>
	<div class="space-y-4">
		{#each group.fields as field (field.key)}
			<ConfigSchemaField {field} bind:value={values[field.key]} />
		{/each}
	</div>
	{#if editable.length > 0}
		<div class="flex items-center gap-3">
			<button onclick={save} disabled={saving} class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:opacity-50">
				{saving ? 'Saving...' : 'Save'}
			</button>
			{#if feedback}
				<span class="text-sm {feedback.type === 'error' ? 'text-red-600 dark:text-red-400' : 'text-gray-500'}">{feedback.message}</span>
			{/if}
		</div>
	{/if}
</section>
