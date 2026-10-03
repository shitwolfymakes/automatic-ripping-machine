<script lang="ts">
	import { onMount, type Snippet } from 'svelte';
	import type { ConfigView, SettingsGroup } from '$lib/types/api.gen';
	import SchemaConfigForm from '$lib/components/settings/SchemaConfigForm.svelte';
	import { fetchSettings } from '$lib/api/settings';
	import { stepGroup } from '$lib/utils/settings-sections';

	// The config fields a step owns, picked from CONFIG_FIELD_META by their
	// setup_step tag and rendered by the same SchemaConfigForm Settings uses
	// (setup spec D5). Steps wrap this and call save()/isSet() on Continue.
	let { step, children }: { step: string; children?: Snippet<[ConfigView]> } = $props();

	let group = $state<SettingsGroup | null>(null);
	let config = $state<ConfigView | null>(null);
	let loadError = $state<string | null>(null);
	let form: SchemaConfigForm | undefined = $state();

	onMount(async () => {
		try {
			const s = await fetchSettings();
			group = stepGroup(s.schema.groups, step);
			config = s.config;
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not load settings';
		}
	});

	export async function save(): Promise<boolean> {
		return form ? form.save() : false;
	}
	export function isSet(key: string): boolean {
		return form ? form.isSet(key) : false;
	}
	export function current(): ConfigView | null {
		return config;
	}
</script>

{#if loadError}
	<p class="alert alert-danger" role="alert">{loadError}</p>
{:else if group && config}
	<section class="panel config-fields-step">
		<SchemaConfigForm bind:this={form} {group} config={config as Record<string, unknown>} deferred bare />
	</section>
	{#if children}{@render children(config)}{/if}
{:else}
	<p class="config-fields-step-loading">Loading...</p>
{/if}

<style>
	.config-fields-step {
		padding: 1.25rem;
	}
	.config-fields-step-loading {
		color: var(--color-text-muted);
	}
</style>
