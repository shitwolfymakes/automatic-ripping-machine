<script lang="ts">
	import type { Catalog, CatalogService, ChannelType } from '$lib/types/notifications';
	import type { ChannelTemplate } from '$lib/types/notifications';
	import type { EventTypeInfo, ScriptInput, BashScriptInfo } from '$lib/api/channels';
	import ConfigureSection from './sections/ConfigureSection.svelte';
	import LabelEnabledRow from './sections/LabelEnabledRow.svelte';
	import EventsSection from './sections/EventsSection.svelte';
	import ServiceDropdown from './ServiceDropdown.svelte';
	import BashTestPanel from './BashTestPanel.svelte';
	import { missingRequirements } from './channelHelpers';
	import Glyph from '$lib/components/Glyph.svelte';

	export interface AddChannelBody {
		type: ChannelType;
		name: string;
		enabled: boolean;
		config: Record<string, unknown>;
		subscribed_events: string[];
		templates: Record<string, ChannelTemplate>;
		serviceId: string | null;
	}

	let {
		catalog,
		eventTypes = [],
		onsave,
		oncancel,
		ontest
	}: {
		catalog: Catalog;
		eventTypes?: EventTypeInfo[];
		onsave: (body: AddChannelBody) => void;
		oncancel: () => void;
		ontest: (body: AddChannelBody) => void;
	} = $props();

	let type = $state<ChannelType>('apprise');
	let serviceId = $state<string | null>(null);
	let name = $state('');
	let enabled = $state(true);
	let config = $state<Record<string, unknown>>({});
	let events = $state<string[]>([]);
	let templates = $state<Record<string, ChannelTemplate>>({});
	let scriptInputs = $state<ScriptInput[]>([]);

	const service = $derived<CatalogService | null>(
		serviceId ? catalog.services.find((s) => s.id === serviceId) ?? null : null
	);

	const missing = $derived(missingRequirements({ type, name, config, events, service, inputs: type === 'bash' ? scriptInputs : undefined }));
	const ready = $derived(missing.length === 0);

	function setType(t: ChannelType) {
		type = t;
		config = {};
		if (t !== 'apprise') serviceId = null;
	}
	function pickService(id: string) {
		serviceId = id;
		config = {};
	}
	function body(): AddChannelBody {
		return { type, name, enabled, config, subscribed_events: events, templates, serviceId };
	}

	const types: { key: ChannelType; label: string; recommended?: boolean }[] = [
		{ key: 'apprise', label: 'Service (Apprise)', recommended: true },
		{ key: 'webhook', label: 'Webhook' },
		{ key: 'bash', label: 'Bash script' }
	];
</script>

<div class="add-channel-form">
	<div class="add-channel-form-header">
		<h3 class="add-channel-form-title">Add notification channel</h3>
		<button type="button" onclick={oncancel} class="btn btn-link add-channel-form-cancel"><Glyph name="x" /> Cancel</button>
	</div>

	<div class="stack add-channel-form-body">
		<fieldset class="add-channel-form-types">
			<legend class="sr-only">Delivery type</legend>
			{#each types as t}
				<label class="channel-type-option" aria-checked={type === t.key}>
					<input type="radio" name="delivery" class="sr-only" aria-label={t.label} checked={type === t.key} onchange={() => setType(t.key)} />
					<span class="channel-type-option-label">{t.label}</span>
					{#if t.recommended}<span class="badge badge-sm channel-type-option-badge">RECOMMENDED</span>{/if}
				</label>
			{/each}
		</fieldset>

		<LabelEnabledRow bind:name bind:enabled />

		{#if type === 'apprise'}
			<div class="panel-section">
				<ServiceDropdown {catalog} selectedId={serviceId} onpick={pickService} />
			</div>
		{/if}

		<ConfigureSection {type} bind:name bind:enabled bind:config {service} showLabelRow={false} onscript={(i: BashScriptInfo | null) => (scriptInputs = i?.inputs ?? [])} />
		<EventsSection bind:selected={events} bind:templates {eventTypes} inputs={scriptInputs} />
		{#if type === 'bash'}
			<BashTestPanel {config} {templates} {events} {eventTypes} inputs={scriptInputs} />
		{/if}
	</div>

	<div class="add-channel-form-footer">
		<span class="add-channel-form-ready" data-ready={ready}>
			{#if ready}<Glyph name="check" class="h-3.5 w-3.5" /> Ready to save{:else}Needs: {missing.join(', ')}{/if}
		</span>
		<div class="cluster">
			<button type="button" onclick={oncancel} class="btn btn-ghost">Cancel</button>
			{#if type !== 'bash'}
				<button type="button" onclick={() => ontest(body())} class="btn">Send test</button>
			{/if}
			<button type="button" disabled={!ready} onclick={() => onsave(body())} class="btn btn-primary">Save channel</button>
		</div>
	</div>
</div>

<style>
	/* Same border/radius/shadow as .panel (an elevated surface), but the
	   original's header/body/footer each carry their own independent padding
	   rather than one uniform pad, so this stays a local shell instead of .panel. */
	.add-channel-form { border: 1px solid var(--color-border-strong); border-radius: var(--radius-xl); background: var(--color-surface); box-shadow: var(--shadow-2); }
	.add-channel-form-header { display: flex; align-items: center; justify-content: space-between; padding: 1rem 1.25rem; border-bottom: 1px solid var(--color-border); }
	.add-channel-form-title { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-primary); }
	.add-channel-form-cancel { font-size: 0.875rem; color: var(--color-text-muted); }
	/* space-y-5 (1.25rem) is wider than .stack's default gap (1rem). */
	.add-channel-form-body { padding: 1.25rem; gap: 1.25rem; }
	.add-channel-form-types { position: relative; display: grid; grid-template-columns: 1fr; gap: 0.75rem; }
	@media (min-width: 640px) { .add-channel-form-types { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
	.add-channel-form-footer { display: flex; align-items: center; justify-content: space-between; padding: 0.875rem 1.25rem; border-top: 1px solid var(--color-border); }
	.add-channel-form-ready { display: flex; align-items: center; gap: 0.25rem; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.add-channel-form-ready[data-ready="true"] { color: var(--color-status-success); }

	/* channel-type-option: a selectable card, one per delivery type. No block
	   covers this shape (a bordered card wrapping a hidden radio input, with
	   an aria-checked state on the label carrying the selected look). */
	.channel-type-option {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-primary-tint-1);
		padding: 1rem;
		cursor: pointer;
	}
	.channel-type-option[aria-checked="true"] { border-color: var(--color-primary); background: var(--color-primary-tint-2); }
	.channel-type-option-label { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-text-secondary); }
	/* badge-sm's default tint-2/primary-text pairing was bg-primary/15
	   text-primary here (fix round 1: the nearest documented tint, tint-3 at
	   20%, was visibly more saturated than the original's literal 15% -
	   color-mix against --color-primary at the exact 15% reproduces it,
	   the same pattern tokens.css itself uses for tint-1/2/3), and the
	   original size (9.5px) sits a hair under badge-sm's 0.625rem. */
	.channel-type-option-badge { position: absolute; top: 0.75rem; right: 0.75rem; background: color-mix(in srgb, var(--color-primary) 15%, transparent); color: var(--color-primary); font-size: 9.5px; letter-spacing: 0.05em; }
</style>
