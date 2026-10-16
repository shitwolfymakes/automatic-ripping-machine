<script lang="ts">
	import type { ConfigFieldMeta } from '$lib/types/api.gen';
	import { previewRows, type DiscKind } from '$lib/utils/identity-card';

	// Settings › Identification › Identity: what ARM does for one disc kind,
	// derived live from the form's values (the disc kind is the card's view state).
	let { kind, values, fields }: { kind: DiscKind; values: Record<string, unknown>; fields: ConfigFieldMeta[] } =
		$props();

	const rows = $derived(previewRows(kind, values, fields));
</script>

<div class="identity-preview" role="group" aria-label="Identity preview" data-testid="identity-preview">
	{#each rows as row (row.key)}
		<div class="identity-preview-row" data-testid="identity-preview-{row.key}">
			<span class="identity-preview-label">{row.label}</span>
			<div class="identity-preview-content">
				{#if row.sentence !== undefined}
					<span class="identity-preview-sentence">{row.sentence}</span>
				{:else}
					<span class="identity-preview-pills">
						{#each row.sources ?? [] as source (source.label)}
							<span class="chip chip-sm identity-preview-pill" data-testid="identity-preview-pill">
								<span class="identity-preview-rank">{source.rank}</span>
								{source.label}
							</span>
						{:else}
							<span class="identity-preview-empty">{row.empty}</span>
						{/each}
					</span>
					<span class="identity-preview-trust">{row.trust}</span>
				{/if}
			</div>
		</div>
	{/each}
</div>

<style>
	.identity-preview {
		display: flex;
		flex-direction: column;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
		font-size: 0.8125rem;
		line-height: 1.25rem;
	}
	.identity-preview-row {
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.25rem;
		padding: 0.625rem 1rem;
	}
	.identity-preview-row + .identity-preview-row {
		border-top: 1px solid var(--color-border);
	}
	.identity-preview-label {
		font-size: 0.6875rem;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--color-text-muted);
	}
	.identity-preview-content {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.375rem 1rem;
		min-width: 0;
	}
	.identity-preview-sentence {
		color: var(--color-text-secondary);
	}
	.identity-preview-pills {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.375rem;
	}
	.identity-preview-pill {
		gap: 0.375rem;
	}
	.identity-preview-rank {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 1.125rem;
		height: 1.125rem;
		padding: 0 0.25rem;
		border-radius: var(--radius-md);
		background: var(--color-primary-tint-3);
		font-size: 0.6875rem;
		font-weight: 600;
		line-height: 1;
	}
	.identity-preview-empty {
		font-style: italic;
		color: var(--color-text-muted);
	}
	.identity-preview-trust {
		color: var(--color-text-muted);
	}
	/* Label left, content right on a wider panel; trust text pushed to the
	   right edge. Stacked on a phone. */
	@media (min-width: 640px) {
		.identity-preview-row {
			grid-template-columns: 7rem 1fr;
			align-items: center;
			gap: 1rem;
		}
		.identity-preview-trust {
			margin-left: auto;
			text-align: right;
		}
	}
</style>
