<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import type { Channel, Catalog } from '$lib/types/notifications';
	import {
		fetchChannels,
		fetchServices,
		fetchEventTypes,
		updateChannel,
		deleteChannel,
		testSendChannel,
		testConfig
	} from '$lib/api/channels';
	import type { EventTypeInfo } from '$lib/api/channels';
	import { addToast } from '$lib/stores/toast.svelte';
	import StatStrip from './StatStrip.svelte';
	import FilterPills from './FilterPills.svelte';
	import { filterCounts, matchesFilter, summaryCounts, type ChannelFilter } from '../../notifications/channel-filters';
	import ChannelList from './ChannelList.svelte';
	import AddChannelForm from './AddChannelForm.svelte';
	import {
		createChannelFromBody,
		runTest,
		testUnsavedBody,
		type AddChannelBody,
		type TestOutcome
	} from '../../notifications/channel-actions';
	import { editorPatch, editorTestPayload, type EditorBody } from '../../notifications/channel-edits';
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

	$effect(() => {
		load();
	});

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
			loadError = errorMessage(e, 'Failed to load channels');
		}
	}

	const counts = $derived(summaryCounts(channels));
	const pillCounts = $derived(filterCounts(channels));
	const visible = $derived(channels.filter((c) => matchesFilter(c, filter)));

	function serviceNameFor(c: Channel): string {
		return c.type === 'apprise' ? 'Service' : c.type;
	}

	async function handleAdd(body: AddChannelBody) {
		try {
			const created = await createChannelFromBody(body);
			channels = [created, ...channels];
			addOpen = false;
			addToast({ tone: 'success', title: 'Channel added', body: `${created.name} is now listening for events.` });
		} catch (e) {
			addToast({ tone: 'error', title: 'Add failed', body: errorMessage(e, 'Unknown error') });
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

	async function handleEditorSave(c: Channel, body: EditorBody) {
		try {
			const updated = await updateChannel(c.id, editorPatch(c, body));
			channels = channels.map((x) => (x.id === c.id ? updated : x));
			addToast({ tone: 'success', title: 'Saved.' });
		} catch (e) {
			addToast({ tone: 'error', title: 'Save failed', body: errorMessage(e, '') });
		}
	}

	// Returns the first real catalog event key, falling back to a known key.
	function firstEventKey(): string {
		return eventTypes[0]?.key ?? 'rip.completed';
	}

	// Toasts how a test send went.
	function toastTestOutcome(outcome: TestOutcome): void {
		if (outcome.ok) addToast({ tone: 'success', title: 'Test delivered' });
		else addToast({ tone: 'error', title: 'Test failed', body: outcome.detail ?? '' });
	}

	async function handleTestSaved(c: Channel) {
		addToast({ tone: 'info', title: `Sending test to ${c.name}...` });
		toastTestOutcome(await runTest(() => testSendChannel(c.id, c.subscribed_events[0] ?? firstEventKey())));
	}

	async function handleTestUnsaved(body: AddChannelBody) {
		toastTestOutcome(await runTest(() => testUnsavedBody(body, body.subscribed_events[0] ?? firstEventKey())));
	}

	async function handleEditorTest(c: Channel, body: EditorBody) {
		const eventType = body.subscribed_events[0] ?? firstEventKey();
		const payload = editorTestPayload(c, body, eventType);
		if (!payload) {
			// Fields unchanged: test the saved channel instead.
			await handleTestSaved(c);
			return;
		}
		toastTestOutcome(await runTest(() => testConfig(payload)));
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
			addToast({ tone: 'error', title: 'Delete failed', body: errorMessage(e, '') });
		}
	}

	function toggleExpand(c: Channel) {
		expandedId = expandedId === c.id ? null : c.id;
	}
</script>

<div class="stack notifications-tab">
	{#if loadError}
		<p class="alert alert-danger notifications-tab-load-error">{loadError}</p>
	{:else if !loaded}
		<div class="notifications-tab-loading">Loading channels...</div>
	{:else}
		<StatStrip total={counts.total} issues={counts.issues} subscribedEvents={counts.subscribedEvents} />

		{#if addOpen}
			<AddChannelForm
				{catalog}
				{eventTypes}
				onsave={handleAdd}
				oncancel={() => (addOpen = false)}
				ontest={handleTestUnsaved}
			/>
		{/if}

		{#if channels.length > 0}
			<div class="panel-section notifications-tab-toolbar">
				<FilterPills active={filter} counts={pillCounts} onselect={(f) => (filter = f)} />
				{#if !addOpen}
					<button
						type="button"
						onclick={() => (addOpen = true)}
						class="btn btn-primary btn-sm notifications-tab-add-btn">+ Add channel</button
					>
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
				<button type="button" onclick={() => (addOpen = true)} class="btn btn-primary notifications-tab-empty-cta"
					>Add your first channel</button
				>
			</div>
		{/if}
	{/if}
</div>

<ConfirmDialog
	open={deleteTarget !== null}
	title="Delete channel?"
	message={deleteTarget ? `${deleteTarget.name} will be removed and stop receiving events. This cannot be undone.` : ''}
	confirmLabel="Delete"
	variant="danger"
	onconfirm={confirmDelete}
	oncancel={() => (deleteTarget = null)}
/>

<style>
	/* space-y-5 (1.25rem), not .stack's default gap (1rem). */
	.notifications-tab {
		gap: 1.25rem;
	}
	.notifications-tab-load-error {
		padding: 0.75rem 1rem;
	}
	.notifications-tab-loading {
		padding: 2rem 0;
		text-align: center;
		color: var(--color-text-faint);
	}
	/* panel-section's own uniform 1rem padding vs this toolbar's px-4 py-3;
	   the original was bg-page, not panel-section's own primary-tint-1. */
	.notifications-tab-toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.75rem 1rem;
		background: var(--color-page);
	}
	/* the original was rounded-md px-3 py-1.5 text-xs (0.375rem radius,
	   0.375rem vertical padding, 1rem bundled line-height) with no border at
	   all; btn-primary's radius-lg, btn-sm's 0.25rem vertical padding and
	   inherited 1.25rem line-height (btn-sm sets font-size but not
	   line-height), and its own 1px border are all a hair off. */
	.notifications-tab-add-btn {
		border: 0;
		border-radius: var(--radius-md);
		padding: 0.375rem 0.75rem;
		line-height: 1rem;
	}
	/* the original was p-8 (2rem all around, matches panel-section's default
	   of 1rem doubled); stated explicitly for clarity. */
	.notifications-tab-empty {
		padding: 2rem;
		text-align: center;
		background: var(--color-page);
	}
	.notifications-tab-empty-title {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-primary);
	}
	.notifications-tab-empty-body {
		margin-top: 0.25rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-secondary);
	}
	.notifications-tab-empty-cta {
		margin-top: 1rem;
	}
</style>
