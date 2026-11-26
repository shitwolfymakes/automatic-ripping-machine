<script lang="ts">
	// One section card of a schema config form: its heading and blurb,
	// the identity card where the section names it, then its columns,
	// fields, note and advanced fields. The form draws each field's row.
	import type { Snippet } from 'svelte';
	import type { ConfigFieldMeta } from '$lib/types/api.gen';
	import type { SectionFieldGroups } from '$lib/settings/sections';

	interface Props {
		/** The section, with its fields split into their layout buckets. */
		section: SectionFieldGroups;
		/** Draws one field's row, given the id of the note that describes it. */
		fieldRow: Snippet<[ConfigFieldMeta, string | undefined]>;
		/** Draws the identity card, for a section that names it. */
		identityCard: Snippet;
	}
	let { section, fieldRow, identityCard }: Props = $props();

	/** Id of the section's note; set only when the section hides its fields' own help. */
	const noteId = $derived(
		section.note && section.hideFieldHelp
			? `section-note-${section.title.toLowerCase().replace(/\W+/g, '-')}`
			: undefined
	);
</script>

<div data-testid="settings-section" class="panel schema-form-section">
	<h3 class="schema-form-section-title">{section.title}</h3>
	{#if section.blurb}
		<p class="schema-form-section-description schema-form-section-blurb">{section.blurb}</p>
	{:else}
		<div class="schema-form-section-blurb"></div>
	{/if}
	{#if section.custom === 'identity'}
		{@render identityCard()}
	{/if}
	{#if section.columns.length > 0}
		<div class="schema-form-section-columns" data-testid="settings-section-columns">
			{#each section.columns as columnFields, i (i)}
				<div class="stack">
					{#each columnFields as field (field.key)}
						{@render fieldRow(field, noteId)}
					{/each}
				</div>
			{/each}
		</div>
	{/if}
	<div class="stack">
		{#each section.fields as field (field.key)}
			{@render fieldRow(field, noteId)}
		{/each}
	</div>
	{#if section.note}
		<p class="schema-form-section-description" id={noteId}>{section.note}</p>
	{/if}
	{#if section.advanced.length > 0}
		<hr class="schema-form-section-advanced-divider" />
		<span class="label-caps schema-form-section-advanced-label">Advanced</span>
		<div class="stack">
			{#each section.advanced as field (field.key)}
				{@render fieldRow(field, noteId)}
			{/each}
		</div>
	{/if}
</div>

<style>
	/* the settings-section panel is p-6 (1.5rem), not .panel's
	   own p-4 (1rem) default. */
	.schema-form-section {
		padding: 1.5rem;
	}
	/* the group/section blurbs are text-sm (0.875rem/1.25rem), not panel-hint's 0.75rem - panel-hint
	   is sized for a note under a form control, a visibly smaller role. */
	.schema-form-section-description {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.schema-form-section-title {
		margin-bottom: 0.25rem;
		font-size: 1rem;
		line-height: 1.5rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.schema-form-section-blurb {
		margin-bottom: 1rem;
	}
	/* columns: side by side on desktop, stacked on mobile - the fit-width
	   minimum (18rem) is what collapses the grid to one column on a narrow
	   panel without a media query. */
	.schema-form-section-columns {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(18rem, 100%), 1fr));
		gap: 1.5rem;
		margin-bottom: 1rem;
	}
	.schema-form-section-advanced-divider {
		margin: 0.5rem 0 1rem;
		border: none;
		border-top: 1px solid var(--color-border);
	}
	.schema-form-section-advanced-label {
		display: block;
		margin-bottom: 0.5rem;
	}
</style>
