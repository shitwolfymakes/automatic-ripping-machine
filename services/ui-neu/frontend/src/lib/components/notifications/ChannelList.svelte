<script lang="ts">
	import type { Channel, Catalog } from '$lib/types/notifications';
	import type { EditorBody } from './ChannelEditor.svelte';
	import type { EventTypeInfo } from '$lib/api/channels';
	import ChannelRow from './ChannelRow.svelte';
	import ChannelEditor from './ChannelEditor.svelte';

	let {
		channels,
		catalog,
		eventTypes = [],
		expandedId,
		serviceNameFor,
		ontoggle,
		ontest,
		onexpand,
		onedit,
		oneditorsave,
		oneditortest,
		ondelete
	}: {
		channels: Channel[];
		catalog: Catalog;
		eventTypes?: EventTypeInfo[];
		expandedId: number | null;
		serviceNameFor: (c: Channel) => string;
		ontoggle?: (c: Channel) => void;
		ontest?: (c: Channel) => void;
		onexpand?: (c: Channel) => void;
		onedit?: (c: Channel) => void;
		oneditorsave?: (c: Channel, body: EditorBody) => void;
		oneditortest?: (c: Channel, body: EditorBody) => void;
		ondelete?: (c: Channel) => void;
	} = $props();
</script>

<div class="channel-list">
	<div class="channel-list-header">
		<span></span><span>Channel</span><span class="hidden channel-list-header-delivery md:block">Last delivery</span><span class="channel-list-header-center">Enabled</span><span class="channel-list-header-center">Actions</span>
	</div>
	{#each channels as c (c.id)}
		<div class="channel-list-row-group">
			<ChannelRow
				channel={c}
				serviceName={serviceNameFor(c)}
				expanded={expandedId === c.id}
				ontoggle={() => ontoggle?.(c)}
				ontest={() => ontest?.(c)}
				onexpand={() => onexpand?.(c)}
				onedit={() => onedit?.(c)}
			/>
			{#if expandedId === c.id}
				<ChannelEditor
					channel={c}
					{catalog}
					{eventTypes}
					onsave={(b) => oneditorsave?.(c, b)}
					ontest={(b) => oneditortest?.(c, b)}
					onclose={() => onexpand?.(c)}
					ondelete={() => ondelete?.(c)}
				/>
			{/if}
		</div>
	{/each}
</div>

<style>
	.channel-list { overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-xl); background: var(--color-surface); }
	/* :global: .list-row is ChannelRow.svelte's own root class (a different component); fixed 64px for the actions column reproduces the original's grid-cols-[44px_1fr_110px_64px_64px] exactly, on both header and row, so they stay aligned (auto resolves independently per grid and shifts them apart - see fix round 1). */
	.channel-list :global(.list-row) { grid-template-columns: 44px 1fr 110px 64px 64px; }
	.channel-list-header {
		display: grid;
		grid-template-columns: 44px 1fr 110px 64px 64px;
		gap: 1rem;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-primary-tint-1);
		padding: 0.5rem 1rem;
		font-size: 10.5px;
		font-weight: 600;
		letter-spacing: var(--eyebrow-tracking);
		text-transform: uppercase;
		color: var(--color-text-muted);
	}
	.channel-list-header-delivery { white-space: nowrap; text-align: right; }
	.channel-list-header-center { text-align: center; }
	.channel-list-row-group { border-bottom: 1px solid var(--color-border); }
	.channel-list-row-group:last-child { border-bottom: 0; }
</style>
