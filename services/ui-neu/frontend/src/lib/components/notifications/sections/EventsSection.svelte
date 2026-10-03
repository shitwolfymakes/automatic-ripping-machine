<script lang="ts">
	import EventSubscriptions from '../EventSubscriptions.svelte';
	import type { ChannelTemplate } from '$lib/types/notifications';
	import type { EventTypeInfo, ScriptInput } from '$lib/api/channels';

	let {
		selected = $bindable(),
		templates = $bindable(),
		eventTypes = [],
		inputs = []
	}: {
		selected: string[];
		templates: Record<string, ChannelTemplate>;
		eventTypes: EventTypeInfo[];
		inputs?: ScriptInput[];
	} = $props();

	function selectAll() { selected = eventTypes.map((e) => e.key); }
	function clear() { selected = []; }
</script>

<div class="panel-section events-section">
	<div class="events-section-header">
		<span class="panel-title events-section-title">Events</span>
		<span class="events-section-actions">
			<button type="button" class="btn btn-link" onclick={selectAll}>Select all</button>
			<span class="events-section-sep">|</span>
			<button type="button" class="btn btn-link" onclick={clear}>Clear</button>
		</span>
	</div>
	<EventSubscriptions bind:selected bind:templates {eventTypes} {inputs} />
</div>

<style>
	.events-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem; }
	.events-section-title { margin-bottom: 0; }
	.events-section-actions { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	/* .btn-link inherits .btn's 0.875rem/500/1.25rem; these actions were the
	   surrounding text-xs muted colour, not link-styled buttons. */
	.events-section-actions .btn-link { font-size: 0.75rem; font-weight: 400; line-height: 1rem; color: inherit; }
	.events-section-actions .btn-link:hover { color: var(--color-primary); }
	.events-section-sep { margin: 0 0.25rem; }
</style>
