<script lang="ts">
	import EventSubscriptions from '../EventSubscriptions.svelte';
	import type { ChannelTemplate } from '$lib/types/notifications';
	import type { EventTypeInfo, ScriptInput } from '$lib/api/channels';

	let {
		selected = $bindable(),
		templates = $bindable(),
		eventTypes = [],
		inputs = [],
		compact = false
	}: {
		selected: string[];
		templates: Record<string, ChannelTemplate>;
		eventTypes: EventTypeInfo[];
		inputs?: ScriptInput[];
		/** Checkboxes only, no per-event message templates (setup walkthrough). */
		compact?: boolean;
	} = $props();

	function toggle(key: string, on: boolean) {
		selected = on ? [...selected, key] : selected.filter((k) => k !== key);
	}

	function selectAll() {
		selected = eventTypes.map((e) => e.key);
	}
	function clear() {
		selected = [];
	}
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
	{#if compact}
		<div class="events-section-compact">
			{#each eventTypes as e (e.key)}
				<label class="field field-row">
					<input
						type="checkbox"
						checked={selected.includes(e.key)}
						onchange={(ev) => toggle(e.key, (ev.currentTarget as HTMLInputElement).checked)}
					/>
					<span>{e.label}</span>
				</label>
			{/each}
		</div>
	{:else}
		<EventSubscriptions bind:selected bind:templates {eventTypes} {inputs} />
	{/if}
</div>

<style>
	.events-section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
	}
	.events-section-title {
		margin-bottom: 0;
	}
	.events-section-actions {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	/* .btn-link inherits .btn's 0.875rem/500/1.25rem; these actions were the
	   surrounding text-xs muted colour, not link-styled buttons. */
	.events-section-actions .btn-link {
		font-size: 0.75rem;
		font-weight: 400;
		line-height: 1rem;
		color: inherit;
	}
	.events-section-actions .btn-link:hover {
		color: var(--color-primary);
	}
	.events-section-compact {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
		gap: 0.5rem 1rem;
	}
	.events-section-sep {
		margin: 0 0.25rem;
	}
</style>
