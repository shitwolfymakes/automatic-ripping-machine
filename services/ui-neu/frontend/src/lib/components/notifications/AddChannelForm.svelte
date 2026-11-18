<script lang="ts">
	import type { Catalog, CatalogService, ChannelType } from '$lib/types/notifications';
	import type { ChannelTemplate } from '$lib/types/notifications';
	import type { EventTypeInfo, ScriptInput, BashScriptInfo } from '$lib/api/channels';
	import ConfigureSection from './sections/ConfigureSection.svelte';
	import LabelEnabledRow from './sections/LabelEnabledRow.svelte';
	import EventsSection from './sections/EventsSection.svelte';
	import ChannelTypePicker from './ChannelTypePicker.svelte';
	import AddChannelFooter from './AddChannelFooter.svelte';
	import ServiceDropdown from './ServiceDropdown.svelte';
	import BashTestPanel from './BashTestPanel.svelte';
	import { missingRequirements } from '../../notifications/channel-helpers';
	import type { AddChannelBody } from '../../notifications/channel-actions';
	import Glyph from '$lib/components/shared/Glyph.svelte';

	// `compact` (setup walkthrough): a service channel only, no header, no
	// Save/Cancel (the parent saves on Continue through getBody()/isReady()),
	// with the three events most people want preselected.
	let {
		catalog,
		eventTypes = [],
		onsave,
		oncancel,
		ontest,
		variant = 'full'
	}: {
		catalog: Catalog;
		eventTypes?: EventTypeInfo[];
		onsave?: (body: AddChannelBody) => void;
		oncancel?: () => void;
		ontest: (body: AddChannelBody) => void;
		variant?: 'full' | 'compact';
	} = $props();

	const COMPACT_EVENTS = ['rip.completed', 'rip.needs_user_input', 'rip.failed'];

	let type = $state<ChannelType>('apprise');
	let serviceId = $state<string | null>(null);
	let name = $state('');
	let enabled = $state(true);
	let config = $state<Record<string, unknown>>({});
	// svelte-ignore state_referenced_locally
	let events = $state<string[]>(variant === 'compact' ? [...COMPACT_EVENTS] : []);
	let templates = $state<Record<string, ChannelTemplate>>({});
	let scriptInputs = $state<ScriptInput[]>([]);

	const service = $derived<CatalogService | null>(
		serviceId ? (catalog.services.find((s) => s.id === serviceId) ?? null) : null
	);

	const missing = $derived(
		missingRequirements({ type, name, config, events, service, inputs: type === 'bash' ? scriptInputs : undefined })
	);
	const ready = $derived(missing.length === 0);

	function setType(t: ChannelType) {
		type = t;
		config = {};
		if (t !== 'apprise') serviceId = null;
	}
	function pickService(id: string) {
		serviceId = id;
		config = {};
		// Compact has no label row: name the channel after its service.
		if (variant === 'compact' && !name.trim()) name = catalog.services.find((s) => s.id === id)?.name ?? id;
	}
	function body(): AddChannelBody {
		return { type, name, enabled, config, subscribed_events: events, templates, serviceId };
	}
	export function getBody(): AddChannelBody {
		return body();
	}
	export function isReady(): boolean {
		return ready;
	}
	/** True once a service is picked (compact: Continue then means "add it"). */
	export function isStarted(): boolean {
		return serviceId !== null;
	}
</script>

<div class="add-channel-form" data-variant={variant}>
	{#if variant === 'full'}
		<div class="add-channel-form-header">
			<h3 class="add-channel-form-title">Add notification channel</h3>
			<button type="button" onclick={() => oncancel?.()} class="btn btn-link add-channel-form-cancel"
				><Glyph name="x" /> Cancel</button
			>
		</div>
	{/if}

	<div class="stack add-channel-form-body">
		{#if variant === 'full'}
			<ChannelTypePicker selected={type} onpick={setType} />

			<LabelEnabledRow bind:name bind:enabled />
		{/if}

		{#if type === 'apprise'}
			<div class="panel-section">
				<ServiceDropdown {catalog} selectedId={serviceId} onpick={pickService} />
			</div>
		{/if}

		<ConfigureSection
			{type}
			bind:name
			bind:enabled
			bind:config
			{service}
			showLabelRow={false}
			onscript={(i: BashScriptInfo | null) => (scriptInputs = i?.inputs ?? [])}
		/>
		{#if variant === 'full' || serviceId}
			<EventsSection
				bind:selected={events}
				bind:templates
				{eventTypes}
				inputs={scriptInputs}
				compact={variant === 'compact'}
			/>
		{/if}
		{#if type === 'bash'}
			<BashTestPanel {config} {templates} {events} {eventTypes} inputs={scriptInputs} />
		{/if}
	</div>

	<AddChannelFooter
		{ready}
		{missing}
		{variant}
		testable={type !== 'bash'}
		{oncancel}
		ontest={() => ontest(body())}
		onsave={() => onsave?.(body())}
	/>
</div>

<style>
	/* Same border/radius/shadow as .panel (an elevated surface), but the
	   original's header/body/footer each carry their own independent padding
	   rather than one uniform pad, so this stays a local shell instead of .panel. */
	.add-channel-form {
		border: 1px solid var(--color-border-strong);
		border-radius: var(--radius-xl);
		background: var(--color-surface);
		box-shadow: var(--shadow-2);
	}
	.add-channel-form-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--color-border);
	}
	.add-channel-form-title {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-primary);
	}
	.add-channel-form-cancel {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	/* space-y-5 (1.25rem) is wider than .stack's default gap (1rem). */
	.add-channel-form-body {
		padding: 1.25rem;
		gap: 1.25rem;
	}
</style>
