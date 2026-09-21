<script lang="ts">
	import EventSubscriptions from '../EventSubscriptions.svelte';
	import type { ChannelTemplate } from '$lib/types/notifications';
	import type { EventTypeInfo } from '$lib/api/channels';

	let {
		selected = $bindable(),
		templates = $bindable(),
		eventTypes = []
	}: { selected: string[]; templates: Record<string, ChannelTemplate>; eventTypes: EventTypeInfo[] } = $props();

	function selectAll() { selected = eventTypes.map((e) => e.key); }
	function clear() { selected = []; }
</script>

<div class="rounded-lg border border-primary/15 bg-page p-4 dark:border-primary/20 dark:bg-primary/5">
	<div class="mb-3 flex items-center justify-between">
		<span class="text-[11px] font-semibold uppercase tracking-[0.12em] text-primary">Events</span>
		<span class="text-xs text-gray-500 dark:text-gray-400">
			<button type="button" class="hover:text-primary" onclick={selectAll}>Select all</button>
			<span class="mx-1">|</span>
			<button type="button" class="hover:text-primary" onclick={clear}>Clear</button>
		</span>
	</div>
	<EventSubscriptions bind:selected bind:templates {eventTypes} />
</div>
