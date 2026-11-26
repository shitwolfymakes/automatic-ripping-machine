<script lang="ts">
	import type { Snippet } from 'svelte';

	// The card frame System health's storage and service cards share.
	let {
		testid,
		status,
		name,
		path,
		description,
		badge,
		chips,
		children
	}: {
		testid: string;
		status: string;
		name: string;
		path?: string;
		description: string;
		badge: Snippet;
		chips: Snippet;
		children?: Snippet;
	} = $props();
</script>

<div class="health-item" data-testid={testid} data-status={status}>
	<div class="health-item-head">
		<div>
			<span class="health-item-name">{name}</span>
			{#if path !== undefined}
				<code class="mono health-item-path">{path}</code>
			{/if}
			<p class="health-item-description">{description}</p>
		</div>
		{@render badge()}
	</div>
	<div class="cluster health-item-chips">
		{@render chips()}
	</div>
	{@render children?.()}
</div>

<style>
	.health-item {
		display: grid;
		gap: 0.5rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 0.875rem 1rem;
	}
	.health-item[data-status='error'],
	.health-item[data-status='warning'] {
		border-color: var(--color-danger);
	}
	.health-item-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.75rem;
	}
	.health-item-name {
		font-weight: 600;
		color: var(--color-text);
	}
	.health-item-path {
		margin-left: 0.5rem;
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
	/* matches System health's description lines */
	.health-item-description {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.health-item-chips {
		gap: 0.375rem;
	}
</style>
