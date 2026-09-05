<script lang="ts">
	import type { SettingsGroup, ConfigFieldMeta } from '$lib/types/api.gen';
	import { saveArmConfig } from '$lib/api/settings';
	import { groupBlurb, sectionFields } from '$lib/utils/settings-sections';
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
	const sections = $derived(sectionFields(group.name, group.fields));
	const blurb = $derived(groupBlurb(group.name));

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

<div class="flex flex-col gap-6">
	<div>
		<h2 class="text-lg font-semibold text-gray-900 dark:text-white">{group.name}</h2>
		{#if blurb}
			<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{blurb}</p>
		{/if}
	</div>

	<section class="space-y-6">
		{#each sections as section (section.title)}
			<div
				data-testid="settings-section"
				class="rounded-lg border border-primary/20 bg-surface p-6 shadow-xs dark:border-primary/20 dark:bg-surface-dark"
			>
				<h3 class="mb-1 text-base font-semibold text-gray-900 dark:text-white">{section.title}</h3>
				{#if section.blurb}
					<p class="mb-4 text-sm text-gray-500 dark:text-gray-400">{section.blurb}</p>
				{:else}
					<div class="mb-4"></div>
				{/if}
				<div class="space-y-4">
					{#each section.fields as field (field.key)}
						<ConfigSchemaField {field} bind:value={values[field.key]} />
					{/each}
				</div>
			</div>
		{/each}
	</section>

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
</div>
