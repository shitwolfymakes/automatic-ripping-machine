<script lang="ts">
	import type { Channel, Catalog, ChannelCreate, AppriseConfig } from '$lib/types/notifications';
	import {
		fetchChannels, fetchServices, fetchEventTypes, createChannel, updateChannel,
		deleteChannel, testSendChannel, composeUrl, testConfig
	} from '$lib/api/channels';
	import type { EventTypeInfo } from '$lib/api/channels';
	import { addToast } from '$lib/stores/toast.svelte';
	import StatStrip from './StatStrip.svelte';
	import FilterPills, { type ChannelFilter } from './FilterPills.svelte';
	import ChannelList from './ChannelList.svelte';
	import AddChannelForm, { type AddChannelBody } from './AddChannelForm.svelte';
	import type { EditorBody } from './ChannelEditor.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';

	let channels = $state<Channel[]>([]);
	let catalog = $state<Catalog>({ featured: [], services: [] });
	let eventTypes = $state<EventTypeInfo[]>([]);
	let loaded = $state(false);
	let loadError = $state<string | null>(null);
	let addOpen = $state(false);
	let expandedId = $state<number | null>(null);
	let filter = $state<ChannelFilter>('all');
	let deleteTarget = $state<Channel | null>(null);

	$effect(() => { load(); });

	// The system in-app channel (ncl_inbox) is the UI notification bell, not an
	// external Apprise destination: it has no URL to test and can't be deleted
	// (the backend 409s it). Its events feed the Notifications page/bell directly.
	// Hide it from this channel-management table — it would only render broken
	// Send-test / Delete actions and a perpetual "never" delivery. It keeps
	// existing and logging server-side; this is purely a display filter.
	const INAPP_CHANNEL_ID = 'ncl_inbox';

	async function load() {
		try {
			const [chans, cat, evts] = await Promise.all([fetchChannels(), fetchServices(), fetchEventTypes()]);
			channels = chans.filter((c) => String(c.id) !== INAPP_CHANNEL_ID);
			catalog = cat;
			eventTypes = evts;
			loaded = true;
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Failed to load channels';
		}
	}

	const counts = $derived({
		total: channels.length,
		issues: channels.filter((c) => c.last_error).length,
		subscribedEvents: new Set(channels.flatMap((c) => c.subscribed_events)).size
	});
	const filterCounts = $derived({
		all: channels.length,
		enabled: channels.filter((c) => c.enabled).length,
		paused: channels.filter((c) => !c.enabled).length,
		issues: channels.filter((c) => c.last_error).length
	});
	const visible = $derived(channels.filter((c) =>
		filter === 'all' ? true :
		filter === 'enabled' ? c.enabled :
		filter === 'paused' ? !c.enabled :
		!!c.last_error
	));

	function serviceNameFor(c: Channel): string {
		return c.type === 'apprise' ? 'Service' : c.type;
	}

	async function toConfig(body: { type: string; config: Record<string, unknown>; serviceId: string | null }) {
		if (body.type === 'apprise' && body.serviceId) {
			// neu composes the url server-side from {service_id, fields}.
			return { type: 'apprise', url: '', service_id: body.serviceId, fields: body.config };
		}
		return { type: body.type, ...body.config };
	}

	async function handleAdd(body: AddChannelBody) {
		try {
			const config = await toConfig(body);
			const payload: ChannelCreate = {
				type: body.type, name: body.name, enabled: body.enabled,
				config: config as ChannelCreate['config'],
				subscribed_events: body.subscribed_events,
				templates: body.templates
			};
			const created = await createChannel(payload);
			channels = [created, ...channels];
			addOpen = false;
			addToast({ tone: 'success', title: 'Channel added', body: `${created.name} is now listening for events.` });
		} catch (e) {
			addToast({ tone: 'error', title: 'Add failed', body: e instanceof Error ? e.message : 'Unknown error' });
		}
	}

	async function handleToggle(c: Channel) {
		const next = !c.enabled;
		channels = channels.map((x) => (x.id === c.id ? { ...x, enabled: next } : x));
		try {
			await updateChannel(c.id, { enabled: next });
			addToast({ tone: 'info', title: next ? `Enabled ${c.name}` : `Paused ${c.name}` });
		} catch {
			channels = channels.map((x) => (x.id === c.id ? { ...x, enabled: c.enabled } : x));
			addToast({ tone: 'error', title: 'Update failed', body: c.name });
		}
	}

	// Has the editor changed the apprise field map vs what's stored? When
	// false the editor handlers omit `config` from the PATCH (save) or
	// fall through to the saved-channel test path so neu keeps the
	// stored url + recompose state intact.
	function appriseFieldsDirty(c: Channel, body: EditorBody): boolean {
		const stored = ((c.config as AppriseConfig).fields ?? {}) as Record<string, unknown>;
		return JSON.stringify(body.appriseFields) !== JSON.stringify(stored);
	}

	async function handleEditorSave(c: Channel, body: EditorBody) {
		try {
			const patch: Record<string, unknown> = {
				name: body.name,
				enabled: body.enabled,
				subscribed_events: body.subscribed_events,
				templates: body.templates
			};
			if (c.type === 'apprise') {
				if (appriseFieldsDirty(c, body) && body.serviceId) {
					patch.config = {
						type: 'apprise',
						url: '',
						service_id: body.serviceId,
						fields: body.appriseFields
					};
				}
				// not dirty -> omit config -> neu keeps stored url + fields
			} else {
				patch.config = body.config as unknown as Channel['config'];
			}
			const updated = await updateChannel(c.id, patch as Parameters<typeof updateChannel>[1]);
			channels = channels.map((x) => (x.id === c.id ? updated : x));
			addToast({ tone: 'success', title: 'Saved.' });
		} catch (e) {
			addToast({ tone: 'error', title: 'Save failed', body: e instanceof Error ? e.message : '' });
		}
	}

	// Returns the first real catalog event key, falling back to a known key.
	function firstEventKey(): string {
		return eventTypes[0]?.key ?? 'rip.completed';
	}

	async function handleTestSaved(c: Channel) {
		addToast({ tone: 'info', title: `Sending test to ${c.name}...` });
		try {
			const res = await testSendChannel(c.id, c.subscribed_events[0] ?? firstEventKey());
			if (res.ok) addToast({ tone: 'success', title: 'Test delivered' });
			else addToast({ tone: 'error', title: 'Test failed', body: res.error ?? '' });
		} catch (e) {
			addToast({ tone: 'error', title: 'Test failed', body: e instanceof Error ? e.message : '' });
		}
	}

	// Test an unsaved/edited config and toast the result. Shared by the add-form
	// and the inline editor so the success/error toast handling lives in one place.
	async function testConfigAndToast(type: string, config: Record<string, unknown>, eventType: string) {
		const res = await testConfig({ type, config, event_type: eventType });
		if (res.ok) addToast({ tone: 'success', title: 'Test delivered' });
		else addToast({ tone: 'error', title: 'Test failed', body: res.error ?? '' });
	}

	async function handleTestUnsaved(body: AddChannelBody) {
		try {
			const config = await toConfig(body);
			await testConfigAndToast(body.type, config, body.subscribed_events[0] ?? firstEventKey());
		} catch (e) {
			addToast({ tone: 'error', title: 'Test failed', body: e instanceof Error ? e.message : '' });
		}
	}

	async function handleEditorTest(c: Channel, body: EditorBody) {
		const eventType = body.subscribed_events[0] ?? firstEventKey();
		try {
			if (c.type === 'apprise') {
				if (appriseFieldsDirty(c, body)) {
					const res = await testConfig({
						channel_id: c.id,
						fields: body.appriseFields,
						event_type: eventType
					});
					if (res.ok) addToast({ tone: 'success', title: 'Test delivered' });
					else addToast({ tone: 'error', title: 'Test failed', body: res.error ?? '' });
					return;
				}
				// Fields unchanged: test the saved channel instead.
				await handleTestSaved(c);
				return;
			}
			// Webhook/bash: test the edited config directly via the unsaved-config
			// endpoint so the user tests their current edits, not the last-saved state.
			await testConfigAndToast(c.type, body.config, eventType);
		} catch (e) {
			addToast({ tone: 'error', title: 'Test failed', body: e instanceof Error ? e.message : '' });
		}
	}

	async function confirmDelete() {
		const c = deleteTarget;
		if (!c) return;
		deleteTarget = null;
		try {
			await deleteChannel(c.id);
			channels = channels.filter((x) => x.id !== c.id);
			if (expandedId === c.id) expandedId = null;
			addToast({ tone: 'info', title: `Deleted ${c.name}` });
		} catch (e) {
			addToast({ tone: 'error', title: 'Delete failed', body: e instanceof Error ? e.message : '' });
		}
	}

	function toggleExpand(c: Channel) { expandedId = expandedId === c.id ? null : c.id; }
</script>

<div class="stack notifications-tab">
	{#if loadError}
		<p class="alert alert-danger notifications-tab-load-error">{loadError}</p>
	{:else if !loaded}
		<div class="notifications-tab-loading">Loading channels...</div>
	{:else}
		<StatStrip total={counts.total} issues={counts.issues} subscribedEvents={counts.subscribedEvents} />

		{#if addOpen}
			<AddChannelForm {catalog} {eventTypes} onsave={handleAdd} oncancel={() => (addOpen = false)} ontest={handleTestUnsaved} />
		{/if}

		{#if channels.length > 0}
			<div class="panel-section notifications-tab-toolbar">
				<FilterPills active={filter} counts={filterCounts} onselect={(f) => (filter = f)} />
				{#if !addOpen}
					<button type="button" onclick={() => (addOpen = true)} class="btn btn-primary btn-sm notifications-tab-add-btn">+ Add channel</button>
				{/if}
			</div>
			<ChannelList
				channels={visible}
				{catalog}
				{eventTypes}
				{expandedId}
				{serviceNameFor}
				ontoggle={handleToggle}
				ontest={handleTestSaved}
				onexpand={toggleExpand}
				onedit={toggleExpand}
				oneditorsave={handleEditorSave}
				oneditortest={handleEditorTest}
				ondelete={(c) => (deleteTarget = c)}
			/>
		{:else if !addOpen}
			<div class="panel-section notifications-tab-empty">
				<p class="notifications-tab-empty-title">No notification channels yet</p>
				<p class="notifications-tab-empty-body">Add one to start receiving alerts for rip and transcode events.</p>
				<button type="button" onclick={() => (addOpen = true)} class="btn btn-primary notifications-tab-empty-cta">Add your first channel</button>
			</div>
		{/if}
	{/if}
</div>

<style>
	/* space-y-5 (1.25rem), not .stack's default gap (1rem). */
	.notifications-tab { gap: 1.25rem; }
	.notifications-tab-load-error { padding: 0.75rem 1rem; }
	.notifications-tab-loading { padding: 2rem 0; text-align: center; color: var(--color-text-faint); }
	/* panel-section's own uniform 1rem padding vs this toolbar's px-4 py-3;
	   the original was bg-page, not panel-section's own primary-tint-1. */
	.notifications-tab-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.75rem 1rem; background: var(--color-page); }
	/* the original was rounded-md px-3 py-1.5 text-xs (0.375rem radius,
	   0.375rem vertical padding, 1rem bundled line-height) with no border at
	   all; btn-primary's radius-lg, btn-sm's 0.25rem vertical padding and
	   inherited 1.25rem line-height (btn-sm sets font-size but not
	   line-height), and its own 1px border are all a hair off. */
	.notifications-tab-add-btn { border: 0; border-radius: var(--radius-md); padding: 0.375rem 0.75rem; line-height: 1rem; }
	/* the original was p-8 (2rem all around, matches panel-section's default
	   of 1rem doubled); stated explicitly for clarity. */
	.notifications-tab-empty { padding: 2rem; text-align: center; background: var(--color-page); }
	.notifications-tab-empty-title { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-primary); }
	.notifications-tab-empty-body { margin-top: 0.25rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-secondary); }
	.notifications-tab-empty-cta { margin-top: 1rem; }
</style>

<ConfirmDialog
	open={deleteTarget !== null}
	title="Delete channel?"
	message={deleteTarget ? `${deleteTarget.name} will be removed and stop receiving events. This cannot be undone.` : ''}
	confirmLabel="Delete"
	variant="danger"
	onconfirm={confirmDelete}
	oncancel={() => (deleteTarget = null)}
/>
