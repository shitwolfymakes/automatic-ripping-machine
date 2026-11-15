<script lang="ts">
	// The sidebar's tab strip: filter box and "Changed only" above it, a count
	// per tab of the inputs it shows under the current filter, a warning glyph on
	// tabs with an issue one of their inputs shows (the banner lists the rest), a count of zero dimmed. The body renders through children, handed the current filter.
	import type { Snippet } from 'svelte';
	import type { HandbrakeSchemaSlimView, HandbrakeSettings, SettingIssue } from '$lib/types/api.gen';
	import Glyph from '$lib/components/Glyph.svelte';
	import { TABS, type TabId } from '$lib/handbrake/fields';
	import { firstTabWithMatch, tabVisibleCounts, type VisibleInput } from '$lib/handbrake/filter';
	import { placedIssues } from '$lib/handbrake/issuePlacement';
	import type { BaseValues } from '$lib/handbrake/sidebarModel';

	interface Props {
		schema: HandbrakeSchemaSlimView;
		settings: HandbrakeSettings;
		base: BaseValues;
		cards: VisibleInput['cards'];
		expanded: string[];
		issues: SettingIssue[];
		tab: TabId;
		ontab: (t: TabId) => void;
		children: Snippet<[{ text: string; changedOnly: boolean }]>;
	}

	let { schema, settings, base, cards, expanded, issues, tab, ontab, children }: Props = $props();

	let text = $state('');
	let changedOnly = $state(false);

	const counts = $derived(tabVisibleCounts({ schema, settings, base, cards, expanded, filter: { text, changedOnly } }));
	const tabByKey = $derived(new Map([...schema.keys, ...schema.audio_item_keys].map((k) => [k.name, k.tab])));
	const placed = $derived(placedIssues(issues, { schema, settings, base, cards, expanded }));
	const issueTabs = $derived(new Set(placed.map((i) => tabByKey.get(i.key))));

	// Only while filtering: clearing the box leaves the user where they are.
	function jumpToMatch() {
		if (text.trim() === '') return;
		ontab(firstTabWithMatch(counts, tab));
	}
	function onfilter(e: Event) {
		text = (e.currentTarget as HTMLInputElement).value;
		jumpToMatch();
	}
</script>

<div class="settings-tabs">
	<div class="settings-tabs-toolbar">
		<input
			type="search"
			class="field-control"
			placeholder="Filter settings"
			aria-label="Filter settings"
			value={text}
			oninput={onfilter}
		/>
		<label class="settings-tabs-changed"
			><input type="checkbox" bind:checked={changedOnly} onchange={jumpToMatch} /> Changed only</label
		>
	</div>
	<div role="tablist" class="settings-tabs-strip">
		{#each TABS as t (t.id)}
			<button type="button" role="tab" aria-selected={tab === t.id} class="settings-tab" onclick={() => ontab(t.id)}>
				{String(t.label)}
				<span class={counts[t.id] === 0 ? 'settings-tab-count settings-tab-count-zero' : 'settings-tab-count'}
					>{counts[t.id]}</span
				>
				{#if issueTabs.has(t.id)}<Glyph name="warning" label="Has issues" class="h-3 w-3" />{/if}
			</button>
		{/each}
	</div>
	<div role="tabpanel">{@render children({ text, changedOnly })}</div>
</div>

<style>
	.settings-tabs-toolbar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding-bottom: 0.5rem;
		margin-bottom: 0.5rem;
		border-bottom: 1px solid var(--color-border);
	}
	.settings-tabs-changed {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		white-space: nowrap;
		font-size: 0.875rem;
		color: var(--color-text-secondary);
	}
	.settings-tabs-strip {
		display: flex;
		flex-wrap: wrap;
		gap: 0 1.125rem;
		margin-bottom: 0.75rem;
		border-bottom: 1px solid var(--color-border);
	}
	.settings-tab {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.5rem 0 0.4rem;
		border-bottom: 2px solid transparent;
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
	.settings-tab[aria-selected='true'] {
		border-bottom-color: var(--color-primary);
		color: var(--color-text);
		font-weight: 600;
	}
	.settings-tab-count {
		color: var(--color-primary-text);
		font-size: 0.6875rem;
		font-variant-numeric: tabular-nums;
	}
	.settings-tab-count-zero {
		opacity: 0.45;
	}
	/* :global because the warning svg is rendered inside the Glyph component. */
	.settings-tab :global(svg) {
		color: var(--color-warning);
	}
</style>
