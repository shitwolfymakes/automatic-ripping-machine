<script lang="ts">
	import type { DocsNavSection } from '$lib/help/api';

	interface Props {
		nav: DocsNavSection[];
		activeId: string;
		open: boolean;
	}

	let { nav, activeId, open = $bindable() }: Props = $props();
</script>

<button
	type="button"
	class="btn btn-sm help-topics-toggle"
	aria-expanded={open}
	aria-controls="help-topics"
	onclick={() => (open = !open)}
>
	Topics
</button>
<nav id="help-topics" class="nav help-topics" data-open={open} aria-label="Help topics">
	{#each nav as section (section.id)}
		<p class="eyebrow help-section">{section.label}</p>
		{#each section.groups as group, gi (gi)}
			{#if group.label}<p class="help-group">{group.label}</p>{/if}
			{#each group.items as item, ii (ii)}
				<a
					class="nav-item"
					href={item.href}
					data-active={item.pageId === activeId ? 'true' : undefined}
					aria-current={item.pageId === activeId ? 'page' : undefined}
					target={item.external ? '_blank' : undefined}
					rel={item.external ? 'noopener' : undefined}>{item.label}</a
				>
			{/each}
		{/each}
	{/each}
</nav>

<style>
	.help-topics {
		padding: 0;
	}
	.help-topics-toggle {
		display: none;
	}
	.help-section {
		margin-top: 0.75rem;
		padding: 0 0.75rem;
	}
	.help-group {
		margin: 0.5rem 0 0;
		padding: 0 0.75rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--color-text-muted);
	}

	@media (max-width: 64rem) {
		.help-topics-toggle {
			display: inline-flex;
		}
		.help-topics:not([data-open='true']) {
			display: none;
		}
	}
</style>
