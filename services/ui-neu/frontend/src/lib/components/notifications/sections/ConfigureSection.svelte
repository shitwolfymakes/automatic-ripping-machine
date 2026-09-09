<script lang="ts">
	import type { CatalogService, ChannelType, CatalogField } from '$lib/types/notifications';
	import type { BashScriptInfo } from '$lib/api/channels';
	import SchemaField from '../SchemaField.svelte';
	import ServiceGlyph from '../ServiceGlyph.svelte';
	import LabelEnabledRow from './LabelEnabledRow.svelte';
	import BashScriptFields from './BashScriptFields.svelte';

	let {
		type,
		name = $bindable(),
		enabled = $bindable(),
		config = $bindable(),
		service,
		showLabelRow = true,
		preserveExisting = false,
		onscript
	}: {
		type: ChannelType;
		name: string;
		enabled: boolean;
		config: Record<string, unknown>;
		service: CatalogService | null;
		showLabelRow?: boolean;
		preserveExisting?: boolean;
		onscript?: (info: BashScriptInfo | null) => void;
	} = $props();

	const webhookFields: CatalogField[] = [
		{ key: 'url', label: 'Webhook URL', type: 'string', private: false, required: true },
		{ key: 'shared_secret', label: 'Shared Secret', type: 'string', private: true, required: false }
	];

	const appriseRequired = $derived(service?.required_fields ?? []);
	const appriseAdvancedAll = $derived(service?.advanced_fields ?? []);
	const appriseAdvancedText = $derived(appriseAdvancedAll.filter((f) => f.type !== 'bool'));
	const appriseAdvancedBool = $derived(appriseAdvancedAll.filter((f) => f.type === 'bool'));

	const flatFields = $derived(type === 'webhook' ? webhookFields : []);

	function applyPreserve(fields: CatalogField[]): CatalogField[] {
		return preserveExisting ? fields.map((f) => ({ ...f, required: false })) : fields;
	}
</script>

<div class="stack">
	{#if showLabelRow}
		<LabelEnabledRow bind:name bind:enabled />
	{/if}

	{#if type === 'apprise' && service}
		<div class="panel-section">
			<div class="panel-title configure-section-title">
				<ServiceGlyph id={service.id} name={service.name} size={18} />
				{service.name} configuration
				<span class="mono configure-section-scheme">{service.url_scheme}://...</span>
			</div>
			{#if preserveExisting}
				<p class="panel-hint configure-section-hint">Re-enter credentials to change the destination. Leave blank to keep the current settings.</p>
			{/if}

			{#if appriseRequired.length}
				<div class="grid-2">
					{#each applyPreserve(appriseRequired) as f (f.key)}
						<SchemaField field={f} bind:value={config[f.key]} />
					{/each}
				</div>
			{/if}

			{#if appriseAdvancedAll.length}
				<details class="configure-section-advanced">
					<summary class="configure-section-advanced-summary">
						Advanced ({appriseAdvancedAll.length})
					</summary>
					<div class="stack stack-sm configure-section-advanced-body">
						{#if appriseAdvancedText.length}
							<div class="grid-2">
								{#each applyPreserve(appriseAdvancedText) as f (f.key)}
									<SchemaField field={f} bind:value={config[f.key]} />
								{/each}
							</div>
						{/if}
						{#if appriseAdvancedBool.length}
							<div class="configure-section-bool-grid">
								{#each applyPreserve(appriseAdvancedBool) as f (f.key)}
									<SchemaField field={f} bind:value={config[f.key]} />
								{/each}
							</div>
						{/if}
					</div>
				</details>
			{/if}
		</div>
	{:else if type === 'bash'}
		<div class="panel-section">
			<div class="panel-title configure-section-title-only">Bash script configuration</div>
			<BashScriptFields bind:config {preserveExisting} {onscript} />
		</div>
	{:else if flatFields.length}
		<div class="panel-section">
			<div class="panel-title configure-section-title-only">
				Webhook configuration
			</div>
			{#if preserveExisting}
				<p class="panel-hint configure-section-hint">Re-enter credentials to change the destination. Leave blank to keep the current settings.</p>
			{/if}
			<div class="grid-2">
				{#each applyPreserve(flatFields) as f (f.key)}
					<div class={f.key === 'url' ? 'configure-section-span-2' : ''}>
						<SchemaField field={f} bind:value={config[f.key]} />
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>

<style>
	.configure-section-scheme { margin-left: 0.25rem; font-size: 11px; text-transform: none; letter-spacing: normal; color: var(--color-text-muted); }
	/* panel-hint's own margin-top (0.75rem) is meant for a note under the whole
	   panel; here it sits directly under the title, replacing the block's mb-3. */
	.configure-section-hint { margin-top: 0; margin-bottom: 0.75rem; }
	.configure-section-title-only { margin-bottom: 0.75rem; }
	.configure-section-advanced { margin-top: 1rem; }
	.configure-section-advanced-summary { cursor: pointer; font-size: 0.75rem; line-height: 1rem; font-weight: 500; color: var(--color-text-muted); }
	.configure-section-advanced-summary:hover { color: var(--color-primary); }
	.configure-section-advanced-body { margin-top: 0.75rem; }
	.configure-section-bool-grid { display: grid; grid-template-columns: 1fr; gap: 0.5rem; padding-top: 0.5rem; border-top: 1px solid var(--color-border); }
	@media (min-width: 640px) { .configure-section-bool-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
	@media (min-width: 768px) { .configure-section-bool-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
	@media (min-width: 640px) { .configure-section-span-2 { grid-column: span 2; } }
</style>
