<script lang="ts">
	import { onMount } from 'svelte';
	import type { Catalog } from '$lib/types/notifications';
	import { fetchServices, fetchEventTypes, type EventTypeInfo } from '$lib/api/channels';
	import { saveArmConfig } from '$lib/api/settings';
	import AddChannelForm, { type AddChannelBody } from './AddChannelForm.svelte';
	import { createChannelFromBody, testUnsavedBody } from './channelActions';
	import StatusStrip from '$lib/components/StatusStrip.svelte';
	import Glyph from '$lib/components/Glyph.svelte';

	// One phone or chat channel, added without leaving the setup walkthrough.
	// The same AddChannelForm Settings > Notifications uses, in its compact
	// variant; the parent calls save() on Continue.
	let catalog = $state<Catalog | null>(null);
	let eventTypes = $state<EventTypeInfo[]>([]);
	let loadError = $state<string | null>(null);
	let form: AddChannelForm | undefined = $state();
	let test = $state<{ tone: 'ok' | 'danger' | 'busy'; title: string; message?: string | null } | null>(null);

	onMount(async () => {
		try {
			[catalog, eventTypes] = await Promise.all([fetchServices(), fetchEventTypes()]);
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not load the notification services.';
		}
	});

	async function sendTest(body: AddChannelBody) {
		test = { tone: 'busy', title: 'Sending a test...' };
		try {
			const res = await testUnsavedBody(body, body.subscribed_events[0] ?? 'rip.completed');
			test = res.ok
				? { tone: 'ok', title: 'Test sent', message: null }
				: { tone: 'danger', title: "The test didn't arrive", message: res.error ?? null };
		} catch (e) {
			test = { tone: 'danger', title: "The test didn't arrive", message: e instanceof Error ? e.message : null };
		}
	}

	/**
	 * Add the channel and switch notifications on. 'empty' when no service was
	 * picked (Continue then means skip); throws when a picked one is incomplete.
	 */
	export async function save(): Promise<'created' | 'empty'> {
		if (!form || !form.isStarted()) return 'empty';
		if (!form.isReady()) throw new Error('Fill in the service fields first, or skip this step.');
		await saveArmConfig({ notifications_enabled: true });
		await createChannelFromBody(form.getBody());
		return 'created';
	}
</script>

<div class="stack channel-quick-add">
	<p class="channel-quick-add-inbox">
		<Glyph name="bell" /> ARM always shows notifications in its own inbox. Add a phone or chat service to get them there too.
	</p>
	{#if loadError}
		<p class="alert alert-danger" role="alert">{loadError}</p>
	{:else if catalog}
		<AddChannelForm bind:this={form} {catalog} {eventTypes} variant="compact" ontest={sendTest} />
		{#if test}
			<StatusStrip tone={test.tone} title={test.title} message={test.message} />
		{/if}
	{:else}
		<p class="field-help">Loading services...</p>
	{/if}
</div>

<style>
	.channel-quick-add-inbox {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
</style>
