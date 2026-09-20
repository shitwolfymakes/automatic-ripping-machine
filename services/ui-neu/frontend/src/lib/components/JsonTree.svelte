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
		string: 'text-gray-900 dark:text-white',
		number: 'text-amber-600 dark:text-amber-400',
		boolean: 'text-gray-400 italic',
		null: 'text-gray-400 italic'
	};
</script>

{#if node.isContainer}
	<div class="font-mono text-xs">
		<button
			type="button"
			onclick={() => { open = !open; }}
			class="flex w-full items-center gap-1 py-0.5 text-left hover:bg-page dark:hover:bg-gray-800/50"
		>
			<svg class="h-3 w-3 shrink-0 transition-transform {open ? 'rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
			</svg>
			{#if name !== undefined}
				<span class="text-gray-500 dark:text-gray-400">{name}</span>
			{/if}
			<span class="text-gray-400 dark:text-gray-500">{node.preview}</span>
		</button>
		{#if open}
			<div class="ml-3 border-l border-primary/15 pl-2 dark:border-primary/15">
				{#each node.entries as entry}
					<Self value={entry.value} name={entry.key} depth={depth + 1} />
				{/each}
			</div>
		{/if}
	</div>
{:else}
	<div class="flex items-baseline gap-1 py-0.5 font-mono text-xs">
		{#if name !== undefined}
			<span class="text-gray-500 dark:text-gray-400">{name}</span><span class="text-gray-400 dark:text-gray-500">:</span>
		{/if}
		<span class={scalarClass[node.kind] ?? 'text-gray-900 dark:text-white'}>{node.preview}</span>
	</div>
{/if}
