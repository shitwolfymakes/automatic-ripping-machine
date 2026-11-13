<script lang="ts">
	import InlineField from '$lib/components/InlineField.svelte';
	import type { EditableJobField, MetadataField } from '$lib/jobs/fields';

	interface Props {
		fields: MetadataField[];
		canEdit: boolean;
		onsave: (field: EditableJobField, raw: string) => Promise<void>;
	}

	let { fields, canEdit, onsave }: Props = $props();
</script>

<div class="job-detail-metadata-grid w-full sm:w-auto flex-1 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
	{#each fields as field, i (field.empty ? `pad-${i}` : field.label)}
		<div class="job-detail-metadata-cell">
			{#if !field.empty}
				<div class="job-detail-metadata-label">{field.label}</div>
				{#if field.link}
					<a
						href={field.link}
						target="_blank"
						rel="noopener noreferrer"
						class="mt-1 block job-detail-metadata-value job-detail-metadata-link {field.mono
							? 'mono job-detail-metadata-mono'
							: ''}">{field.value}</a
					>
				{:else if field.edit}
					<div class="mt-1 job-detail-metadata-value" data-testid="fact-{field.edit}">
						<InlineField
							label={field.label}
							value={field.raw ?? ''}
							type="number"
							{canEdit}
							onsave={(raw) => onsave(field.edit!, raw)}
						/>
					</div>
				{:else}
					<div
						class="mt-1 job-detail-metadata-value {field.mono ? 'mono job-detail-metadata-mono truncate' : ''}"
						title={field.mono ? field.value : undefined}
					>
						{field.value}
					</div>
				{/if}
			{/if}
		</div>
	{/each}
</div>

<style>
	.job-detail-metadata-cell {
		border-bottom: 1px solid var(--color-border);
		border-right: 1px solid var(--color-border);
		padding: 0.75rem 1rem;
	}
	.job-detail-metadata-cell:nth-child(2n) {
		border-right-width: 0;
	}
	@media (min-width: 640px) {
		.job-detail-metadata-cell:nth-child(2n) {
			border-right-width: 1px;
		}
		.job-detail-metadata-cell:nth-child(3n) {
			border-right-width: 0;
		}
	}
	@media (min-width: 1024px) {
		.job-detail-metadata-cell:nth-child(3n) {
			border-right-width: 1px;
		}
		.job-detail-metadata-cell:nth-child(4n) {
			border-right-width: 0;
		}
	}
	.job-detail-metadata-label {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--color-text-muted);
	}
	.job-detail-metadata-value {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-text);
	}
	.job-detail-metadata-link {
		color: var(--color-primary);
	}
	.job-detail-metadata-link:hover {
		text-decoration: underline;
	}
	.job-detail-metadata-mono {
		font-size: 0.75rem;
		line-height: 1rem;
	}
</style>
