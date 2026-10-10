<script lang="ts">
	import { classifyJsonValue } from '$lib/utils/json-tree';
	import Self from './JsonTree.svelte';

	interface Props {
		value: unknown;
		name?: string;
		depth?: number;
	}
	let { value, name, depth = 0 }: Props = $props();

	let node = $derived(classifyJsonValue(value));
	// Top level expanded, nested collapsed: a container opens when depth <= 1.
	// $state(expr) evaluates the initial-prop expression once at construction,
	// so this seeds the open state from the depth rule and the user's clicks
	// take over thereafter. Each child <Self> is a fresh instance with its own
	// `open`, so the seed runs per node at its own depth.
	let open = $state(classifyJsonValue(value).isContainer && depth <= 1);

	const scalarClass: Record<string, string> = {
		string: 'json-tree-string',
		number: 'json-tree-number',
		boolean: 'json-tree-const',
		null: 'json-tree-const'
	};
</script>

{#if node.isContainer}
	<div class="mono json-tree-node">
		<button type="button" onclick={() => { open = !open; }} class="json-tree-toggle flex w-full items-center gap-1" aria-expanded={open}>
			<svg class="json-tree-chevron h-3 w-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
			</svg>
			{#if name !== undefined}
				<span class="json-tree-key">{name}</span>
			{/if}
			<span class="json-tree-preview">{node.preview}</span>
		</button>
		{#if open}
			<div class="json-tree-children ml-3">
				{#each node.entries as entry}
					<Self value={entry.value} name={entry.key} depth={depth + 1} />
				{/each}
			</div>
		{/if}
	</div>
{:else}
	<div class="mono json-tree-node json-tree-scalar flex items-baseline gap-1">
		{#if name !== undefined}
			<span class="json-tree-key">{name}</span><span class="json-tree-preview">:</span>
		{/if}
		<span class={scalarClass[node.kind] ?? 'json-tree-string'}>{node.preview}</span>
	</div>
{/if}

<style>
	/* .mono is size-neutral; this was font-mono text-xs (0.75rem/1rem). */
	.json-tree-node { font-size: 0.75rem; line-height: 1rem; }
	.json-tree-toggle { padding: 0.125rem 0; text-align: left; border: 0; background: none; cursor: pointer; color: inherit; font: inherit; }
	.json-tree-toggle:hover { background: var(--color-primary-tint-1); }
	.json-tree-chevron { transition: transform var(--motion-fast) var(--ease); }
	.json-tree-toggle[aria-expanded="true"] .json-tree-chevron { transform: rotate(90deg); }
	.json-tree-children { padding-left: 0.5rem; border-left: 1px solid var(--color-border); }
	.json-tree-scalar { padding: 0.125rem 0; }
	.json-tree-key { color: var(--color-text-muted); }
	.json-tree-preview { color: var(--color-text-faint); }
	.json-tree-string { color: var(--color-text); }
	.json-tree-number { color: var(--color-on-warning-soft); }
	.json-tree-const { color: var(--color-text-faint); font-style: italic; }
</style>
