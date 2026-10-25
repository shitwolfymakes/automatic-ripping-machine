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
			{#if row.sentence !== undefined}
				<span class="identity-preview-sentence">{row.sentence}</span>
			{:else}
				<span class="identity-preview-pills">
					{#each row.sources ?? [] as source (source.label)}
						<span class="identity-preview-pill" data-testid="identity-preview-pill">
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
	{/each}
</div>

<style>
	.identity-preview {
		display: flex;
		flex-direction: column;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--color-primary) 6%, var(--color-surface));
		line-height: 1.375rem;
	}
	/* One column on a phone: label, pills, then the trust text under them. */
	.identity-preview-row {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 0.5rem;
		padding: 0.875rem 1.5rem;
	}
	.identity-preview-row + .identity-preview-row {
		border-top: 1px solid var(--color-border);
	}
	.identity-preview-label {
		font-size: 0.9375rem;
		color: var(--color-text-muted);
	}
	.identity-preview-sentence {
		font-size: 1rem;
		color: var(--color-text);
	}
	.identity-preview-pills {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		min-width: 0;
	}
	.identity-preview-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.25rem 0.875rem 0.25rem 0.25rem;
		border: 1px solid var(--color-border);
		border-radius: 999px;
		background: transparent;
		font-size: 1rem;
		color: var(--color-text);
	}
	.identity-preview-rank {
		display: grid;
		place-items: center;
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 50%;
		background: color-mix(in srgb, var(--color-primary) 15%, transparent);
		color: var(--color-primary);
		font-size: 0.75rem;
		font-weight: 600;
		line-height: 1;
	}
	.identity-preview-empty {
		font-size: 0.9375rem;
		font-style: italic;
		color: var(--color-text-muted);
	}
	.identity-preview-trust {
		font-size: 0.9375rem;
		color: var(--color-text-muted);
	}
	/* Label, pills and trust text in three columns on a wider panel. */
	@media (min-width: 640px) {
		.identity-preview-row {
			grid-template-columns: 8rem minmax(0, 1fr) auto;
			align-items: center;
			gap: 1rem;
		}
		.identity-preview-sentence {
			grid-column: 2 / -1;
		}
		.identity-preview-trust {
			text-align: right;
		}
	}
</style>
