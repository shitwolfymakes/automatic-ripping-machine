<script lang="ts" module>
	export interface RecipeCell {
		label: string;
		value?: string | null;
		sub?: string | null;
		mono?: boolean;
		empty?: string;
	}
</script>

<script lang="ts">
	import Glyph from '$lib/components/Glyph.svelte';

	// The rip > transcode > output strip: Settings > Sessions cards and the
	// setup walkthrough's "What happens to each kind of disc" table. Cells sit
	// side by side on desktop and stack on mobile, where the chevron rotates.
	let { cells }: { cells: RecipeCell[] } = $props();
</script>

<div class="recipe-strip">
	{#each cells as cell, i (i)}
		{#if i > 0}
			<div class="recipe-strip-arrow" aria-hidden="true"><Glyph name="chevron-right" /></div>
		{/if}
		<div class="recipe-strip-cell">
			<span class="recipe-strip-label">{cell.label}</span>
			{#if cell.value}
				<span class={cell.mono ? 'mono recipe-strip-path' : 'recipe-strip-value'}>{cell.value}</span>
				{#if cell.sub}<span class="recipe-strip-sub">{cell.sub}</span>{/if}
			{:else}
				<span class="recipe-strip-empty">{cell.empty ?? 'None'}</span>
			{/if}
		</div>
	{/each}
</div>

<style>
	/* the original recipe container used a black/20 wash; --color-backdrop
	   (fixed black in both themes) scaled via color-mix stands in for it. */
	.recipe-strip {
		display: grid;
		grid-template-columns: 1fr;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--color-backdrop) 20%, transparent);
		font-size: 0.75rem;
		line-height: 1rem;
	}
	:global(.dark) .recipe-strip {
		background: color-mix(in srgb, var(--color-backdrop) 33%, transparent);
	}
	@media (min-width: 640px) {
		.recipe-strip {
			grid-auto-flow: column;
			grid-template-columns: none;
			grid-auto-columns: minmax(0, 1fr);
		}
		.recipe-strip > .recipe-strip-arrow {
			width: 1.5rem;
		}
		.recipe-strip > :not(:first-child) {
			border-left: 1px solid var(--color-border);
		}
		.recipe-strip > .recipe-strip-arrow + .recipe-strip-cell {
			border-left: 0;
		}
	}
	.recipe-strip-cell {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		min-width: 0;
		padding: 0.75rem 1rem;
	}
	.recipe-strip-label {
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.025em;
		color: var(--color-text-faint);
	}
	.recipe-strip-value {
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.recipe-strip-sub {
		color: var(--color-text-muted);
	}
	.recipe-strip-empty {
		font-style: italic;
		color: var(--color-text-faint);
	}
	.recipe-strip-path {
		word-break: break-all;
		color: var(--color-text-secondary);
	}
	/* Separator is a glyph icon, never a text character. Stacked on mobile,
	   it turns to point down the column. */
	.recipe-strip-arrow {
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--color-text-faint);
	}
	.recipe-strip-arrow :global(svg) {
		transform: rotate(90deg);
	}
	@media (min-width: 640px) {
		.recipe-strip-arrow :global(svg) {
			transform: none;
		}
	}
</style>
