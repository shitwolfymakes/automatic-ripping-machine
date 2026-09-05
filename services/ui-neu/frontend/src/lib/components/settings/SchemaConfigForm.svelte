<script lang="ts">
	import { onMount } from 'svelte';
	import type { SettingsGroup, ConfigFieldMeta, KeyCheckResponse } from '$lib/types/api.gen';
	import { saveArmConfig, checkApiKey } from '$lib/api/settings';
	import { groupBlurb, sectionFields, KEY_CHECK_NAMES } from '$lib/utils/settings-sections';
	import { formatDateTime } from '$lib/utils/format';
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

	// -------------------------------------------------------------------
	// Per-key API key check (Settings > Metadata > API keys). Fields in
	// KEY_CHECK_NAMES get a Check/Status button + inline result line.
	// -------------------------------------------------------------------
	let keyCheckRunning = $state<Record<string, boolean>>({});
	let keyCheckResult = $state<Record<string, KeyCheckResponse | null>>({});

	function unsavedValueFor(fieldKey: string): string | undefined {
		const v = values[fieldKey];
		if (typeof v !== 'string' || v === '' || v === HIDDEN) return undefined;
		if (v === config[fieldKey]) return undefined;
		return v;
	}

	async function runKeyCheck(fieldKey: string) {
		const name = KEY_CHECK_NAMES[fieldKey];
		if (!name) return;
		keyCheckRunning = { ...keyCheckRunning, [fieldKey]: true };
		try {
			const result = await checkApiKey(name, unsavedValueFor(fieldKey));
			keyCheckResult = { ...keyCheckResult, [fieldKey]: result };
		} catch (e) {
			keyCheckResult = {
				...keyCheckResult,
				[fieldKey]: {
					name,
					status: 'error',
					detail: e instanceof Error ? e.message : 'check failed',
					checked_at: null
				}
			};
		} finally {
			keyCheckRunning = { ...keyCheckRunning, [fieldKey]: false };
		}
	}

	// The makemkv row reports the ripper's last verdict rather than probing a
	// live service, so it runs once on mount with no user action needed.
	onMount(() => {
		if (group.fields.some((f) => f.key === 'makemkv_key')) {
			runKeyCheck('makemkv_key');
		}
	});
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
						{#if field.key in KEY_CHECK_NAMES}
							<ConfigSchemaField {field} bind:value={values[field.key]}>
								{#snippet action()}
									<button
										type="button"
										onclick={() => runKeyCheck(field.key)}
										disabled={keyCheckRunning[field.key]}
										class="shrink-0 rounded-lg border border-primary/20 px-3 py-2 text-sm text-gray-700 hover:bg-primary/5 disabled:opacity-50 dark:border-primary/20 dark:text-gray-300 dark:hover:bg-primary/10"
									>
										{keyCheckRunning[field.key]
											? 'Checking...'
											: field.key === 'makemkv_key'
												? 'Status'
												: 'Check'}
									</button>
								{/snippet}
							</ConfigSchemaField>
							<div class="text-sm" data-testid="key-check-{field.key}">
								{#if keyCheckResult[field.key]}
									{@const result = keyCheckResult[field.key]}
									{#if result?.status === 'ok'}
										<span class="flex items-center gap-1.5 text-green-600 dark:text-green-400">
											<svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
												<path
													fill-rule="evenodd"
													d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
													clip-rule="evenodd"
												/>
											</svg>
											Valid{#if result.checked_at} &middot; checked {formatDateTime(result.checked_at)}{/if}
										</span>
									{:else if result?.status === 'invalid'}
										<span class="flex items-center gap-1.5 text-red-600 dark:text-red-400">
											<svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
												<path
													fill-rule="evenodd"
													d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
													clip-rule="evenodd"
												/>
											</svg>
											{result.detail}
										</span>
									{:else if result?.status === 'missing'}
										<span class="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
											<svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
												<path
													fill-rule="evenodd"
													d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
													clip-rule="evenodd"
												/>
											</svg>
											No key set
										</span>
									{:else if result?.status === 'unknown'}
										<span class="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
											<svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
												<path
													fill-rule="evenodd"
													d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
													clip-rule="evenodd"
												/>
											</svg>
											{result.detail}
										</span>
									{:else if result}
										<span class="flex items-center gap-1.5 text-red-600 dark:text-red-400">
											<svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
												<path
													fill-rule="evenodd"
													d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
													clip-rule="evenodd"
												/>
											</svg>
											{result.detail}
										</span>
									{/if}
								{/if}
							</div>
						{:else}
							<ConfigSchemaField {field} bind:value={values[field.key]} />
						{/if}
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
