<script lang="ts">
		import type { SettingsGroup, ConfigFieldMeta, KeyCheckResponse } from '$lib/types/api.gen';
	import { saveArmConfig, checkApiKey } from '$lib/api/settings';
	import { groupBlurb, sectionFields, KEY_CHECK_NAMES } from '$lib/utils/settings-sections';
	import { formatDateTime } from '$lib/utils/format';
	import ConfigSchemaField from './ConfigSchemaField.svelte';
	import Glyph from '$lib/components/Glyph.svelte';

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

</script>

<div class="flex flex-col gap-6">
	<div>
		<h2 class="schema-config-form-title">{group.name}</h2>
		{#if blurb}
			<p class="schema-config-form-description mt-1">{blurb}</p>
		{/if}
	</div>

	<section class="stack stack-lg">
		{#each sections as section (section.title)}
			<div
				data-testid="settings-section"
				class="panel schema-config-form-panel"
			>
				<h3 class="schema-config-form-section-title">{section.title}</h3>
				{#if section.blurb}
					<p class="schema-config-form-description schema-config-form-section-blurb">{section.blurb}</p>
				{:else}
					<div class="schema-config-form-section-blurb"></div>
				{/if}
				<div class="stack">
					{#each section.fields as field (field.key)}
						{#if field.key in KEY_CHECK_NAMES}
							<ConfigSchemaField {field} bind:value={values[field.key]}>
								{#snippet action()}
									<button
										type="button"
										onclick={() => runKeyCheck(field.key)}
										disabled={keyCheckRunning[field.key]}
										class="btn schema-config-form-key-check-btn"
									>
										{keyCheckRunning[field.key] ? 'Checking...' : 'Check API Key'}
									</button>
								{/snippet}
							</ConfigSchemaField>
							<div class="schema-config-form-key-check" data-testid="key-check-{field.key}" data-empty={!keyCheckResult[field.key]}>
								{#if keyCheckResult[field.key]}
									{@const result = keyCheckResult[field.key]}
									{#if result?.status === 'ok'}
										<span class="flex items-center gap-1.5 schema-config-form-key-check-success">
											<Glyph name="check-circle" class="shrink-0" />
											Valid{#if result.detail}, {result.detail}{/if}{#if result.checked_at}<span class="mx-1">&middot;</span>checked {formatDateTime(result.checked_at)}{/if}
										</span>
									{:else if result?.status === 'invalid'}
										<span class="flex items-center gap-1.5 schema-config-form-key-check-danger">
											<Glyph name="x-circle" class="shrink-0" />
											{result.detail}
										</span>
									{:else if result?.status === 'missing'}
										<span class="flex items-center gap-1.5 schema-config-form-key-check-muted">
											<Glyph name="info" class="shrink-0" />
											No key set
										</span>
									{:else if result?.status === 'unknown'}
										<span class="flex items-center gap-1.5 schema-config-form-key-check-warning">
											<Glyph name="question-circle" class="shrink-0" />
											{result.detail}
										</span>
									{:else if result}
										<span class="flex items-center gap-1.5 schema-config-form-key-check-danger">
											<Glyph name="x-circle" class="shrink-0" />
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
			<button onclick={save} disabled={saving} class="btn btn-primary">
				{saving ? 'Saving...' : 'Save'}
			</button>
			{#if feedback}
				<span class="schema-config-form-feedback" data-error={feedback.type === 'error'}>{feedback.message}</span>
			{/if}
		</div>
	{/if}
</div>

<style>
	.schema-config-form-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	/* the original settings-section panel was p-6 (1.5rem), not .panel's
	   own p-4 (1rem) default. */
	.schema-config-form-panel { padding: 1.5rem; }
	/* the original group/section blurbs were text-sm (0.875rem/1.25rem),
	   not panel-hint's 0.75rem - panel-hint is sized for a note under a
	   form control, a visibly smaller role. */
	.schema-config-form-description { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.schema-config-form-section-title { margin-bottom: 0.25rem; font-size: 1rem; line-height: 1.5rem; font-weight: 600; color: var(--color-text); }
	.schema-config-form-section-blurb { margin-bottom: 1rem; }
	.schema-config-form-key-check { font-size: 0.875rem; line-height: 1.25rem; }
	/* .stack's flex gap is unconditional between every child, unlike the
	   original margin-based space-y-4 stack, where this div's own top/bottom
	   margins collapsed through it when it held no content (an empty block
	   box with no border/padding) - display:none removes it from the flex
	   layout entirely so an empty result row costs no gap, matching that
	   collapse instead of adding a second, uncollapsed gap unit. */
	.schema-config-form-key-check[data-empty="true"] { display: none; }
	.schema-config-form-key-check-success { color: var(--color-success); }
	.schema-config-form-key-check-danger { color: var(--color-danger); }
	.schema-config-form-key-check-warning { color: var(--color-on-warning-soft); }
	.schema-config-form-key-check-muted { color: var(--color-text-muted); }
	.schema-config-form-feedback { font-size: 0.875rem; color: var(--color-text-muted); }
	.schema-config-form-feedback[data-error="true"] { color: var(--color-danger); }
	/* the original was px-3 py-2 text-sm - .btn's own default size, not
	   .btn-sm's compact one, but at a 0.75rem horizontal padding rather
	   than .btn's 1rem. Its border was border-primary/20 (--color-border)
	   with muted text (text-gray-700), not .btn's default
	   border-primary-strong + primary text. It never wrapped, so keep the
	   label on one line at the narrow mobile width. */
	.schema-config-form-key-check-btn { white-space: nowrap; padding-inline: 0.75rem; border-color: var(--color-border); color: var(--color-text-secondary); }
</style>
