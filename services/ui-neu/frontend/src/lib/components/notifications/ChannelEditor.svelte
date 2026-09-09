<script lang="ts">
	import type { Channel, Catalog, CatalogService, AppriseConfig } from '$lib/types/notifications';
	import type { ChannelTemplate } from '$lib/types/notifications';
	import type { EventTypeInfo, ScriptInput, BashScriptInfo } from '$lib/api/channels';
	import ConfigureSection from './sections/ConfigureSection.svelte';
	import EventsSection from './sections/EventsSection.svelte';
	import BashTestPanel from './BashTestPanel.svelte';

	export interface EditorBody {
		name: string;
		enabled: boolean;
		config: Record<string, unknown>;
		subscribed_events: string[];
		templates: Record<string, ChannelTemplate>;
		appriseFields: Record<string, unknown>;
		serviceId: string | null;
	}

	let {
		channel,
		catalog,
		eventTypes = [],
		onsave,
		ontest,
		onclose,
		ondelete
	}: {
		channel: Channel;
		catalog: Catalog;
		eventTypes?: EventTypeInfo[];
		onsave: (body: EditorBody) => void;
		ontest: (body: EditorBody) => void;
		onclose: () => void;
		ondelete: () => void;
	} = $props();

	let name = $state(channel.name);
	let enabled = $state(channel.enabled);
	let config = $state<Record<string, unknown>>({ ...channel.config });
	let events = $state<string[]>([...channel.subscribed_events]);
	// Deep copy: a shallow spread shares the per-event objects with the prop, so
	// editing a title/body/input would mutate `channel.templates` too and the
	// dirty check below would never fire.
	let templates = $state<Record<string, ChannelTemplate>>(
		structuredClone($state.snapshot(channel.templates)) as Record<string, ChannelTemplate>
	);
	let scriptInputs = $state<ScriptInput[]>([]);

	// Apprise channels store config.service_id, so resolve the service from the
	// loaded catalog to render the per-service re-entry fields.
	const serviceId = $derived(
		channel.type === 'apprise'
			? ((channel.config as AppriseConfig).service_id ?? null)
			: null
	);
	const service = $derived<CatalogService | null>(
		serviceId ? catalog.services.find((s) => s.id === serviceId) ?? null : null
	);
	const unknownService = $derived(
		channel.type === 'apprise' && serviceId !== null && service === null
	);

	// Apprise re-entry values live in a separate state from config (which holds the
	// composed url + service_id). Seed from stored fields so private values show as
	// <hidden> (SchemaField renders that as empty + placeholder), and non-private
	// values are pre-filled. Empty appriseFields = keep current destination.
	let appriseFields = $state<Record<string, unknown>>({
		...((channel.config as AppriseConfig).fields ?? {})
	});
	const noFields = $derived(
		channel.type === 'apprise' && !(channel.config as AppriseConfig).fields
	);
	const appriseTouched = $derived(
		Object.values(appriseFields).some((v) => v !== undefined && v !== null && String(v).trim() !== '')
	);

	const dirty = $derived(
		name !== channel.name ||
		enabled !== channel.enabled ||
		(channel.type !== 'apprise' && JSON.stringify(config) !== JSON.stringify(channel.config)) ||
		JSON.stringify(events) !== JSON.stringify(channel.subscribed_events) ||
		JSON.stringify(templates) !== JSON.stringify(channel.templates) ||
		appriseTouched
	);

	function body(): EditorBody {
		return { name, enabled, config, subscribed_events: events, templates, appriseFields, serviceId };
	}
</script>

<div class="stack channel-editor">
	{#if channel.type === 'apprise'}
		{#if unknownService}
			<p class="alert alert-warning">
				Unknown service '{serviceId}' - recreate this channel to edit its destination.
			</p>
		{:else if noFields}
			<p class="alert alert-warning">
				This channel was added via a raw URL. Delete and re-add it to edit its destination.
			</p>
		{:else}
			<ConfigureSection type="apprise" bind:name bind:enabled bind:config={appriseFields} {service} preserveExisting />
		{/if}
	{:else}
		<ConfigureSection type={channel.type} bind:name bind:enabled bind:config {service} preserveExisting onscript={(i: BashScriptInfo | null) => (scriptInputs = i?.inputs ?? [])} />
	{/if}
	<EventsSection bind:selected={events} bind:templates {eventTypes} inputs={scriptInputs} />
	{#if channel.type === 'bash'}
		<BashTestPanel {config} {templates} {events} {eventTypes} channelId={String(channel.id)} inputs={scriptInputs} />
	{/if}

	<div class="cluster">
		<button type="button" disabled={!dirty} onclick={() => onsave(body())} class="btn btn-primary">Save changes</button>
		{#if channel.type !== 'bash'}
			<button type="button" onclick={() => ontest(body())} class="btn">Send test</button>
		{/if}
		<button type="button" onclick={onclose} class="btn">Close</button>
		<button type="button" onclick={ondelete} class="btn btn-danger channel-editor-delete">Delete</button>
	</div>
</div>

<style>
	.channel-editor { border-top: 1px solid var(--color-border); padding: 1rem; }
	/* the original Close button's border was a genuinely neutral grey
	   (border-gray-300/600), not the primary-tinted --color-border-strong
	   every other bare .btn uses - no neutral-border role exists in spec 5.1,
	   so this is a deliberate, unfixable-without-inventing-a-token collapse
	   (kept as bare .btn per the reference's precedent, spec section 3). */
	.channel-editor-delete { margin-left: auto; }
</style>
