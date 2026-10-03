<script lang="ts">
	export type ChannelFilter = 'all' | 'enabled' | 'paused' | 'issues';
	let {
		active,
		counts,
		onselect
	}: {
		active: ChannelFilter;
		counts: Record<ChannelFilter, number>;
		onselect?: (f: ChannelFilter) => void;
	} = $props();

	const pills: { key: ChannelFilter; label: string }[] = [
		{ key: 'all', label: 'All' },
		{ key: 'enabled', label: 'Enabled' },
		{ key: 'paused', label: 'Paused' },
		{ key: 'issues', label: 'Issues' }
	];
</script>

<div class="filter-pills inline-flex gap-1">
	{#each pills as p}
		<button type="button" onclick={() => onselect?.(p.key)} aria-pressed={active === p.key} class="chip">
			{p.label} | {counts[p.key]}
		</button>
	{/each}
</div>

<style>
	.filter-pills { border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-page); padding: 0.125rem; }
	/* Inside this bordered pill-group the chip block's default looks (tint-2
	   background at rest, solid-fill white-on-blue when pressed, and a smaller
	   padding than this group's pills ever had) are too loud next to the
	   group's own border: pills here keep their original px-2.5 py-1 text-xs
	   size, stay plain text at rest, and get only a light primary-tint-3
	   highlight (not a solid fill) when active. */
	.filter-pills .chip {
		padding: 0.25rem 0.625rem;
		font-size: 0.75rem;
		line-height: 1rem;
		background: none;
		color: var(--color-text-muted);
	}
	.filter-pills .chip:hover { background: var(--color-primary-tint-2); color: var(--color-text); }
	.filter-pills .chip[aria-pressed="true"] { background: var(--color-primary-tint-3); color: var(--color-primary); }
</style>
