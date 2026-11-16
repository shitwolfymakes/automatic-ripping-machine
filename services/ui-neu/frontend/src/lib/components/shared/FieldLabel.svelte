<script lang="ts">
	import type { Snippet } from 'svelte';
	import FieldDocsLink from './FieldDocsLink.svelte';
	import type { DocsLink } from '$lib/docs/field-docs';

	// A field's <label for> with its docs "i" beside it. Marks (the "*" of a
	// `required` field, then the `marks` snippet: "(optional)", a unit) sit
	// between the label and the "i", outside the label and the link's name.
	// `children` trail after the "i" (a "Changed" chip, a Reset button). Without
	// `for` (a read-only value, a list with no single control) the name is a
	// plain caption.
	interface Props {
		for?: string;
		// The bare label, also the docs link's accessible name.
		label: string;
		// Registry id of the field; without one no docs link is shown.
		docsId?: string;
		docsFallbackId?: string;
		docsLink?: DocsLink | null;
		docsTitle?: string;
		required?: boolean;
		marks?: Snippet;
		children?: Snippet;
	}

	let {
		for: htmlFor,
		label,
		docsId,
		docsFallbackId,
		docsLink,
		docsTitle,
		required = false,
		marks,
		children
	}: Props = $props();
</script>

<div class="field-label-row">
	{#if htmlFor === undefined}
		<span class="field-label">{label}</span>
	{:else}
		<label class="field-label" for={htmlFor}>{label}</label>
	{/if}
	{#if required}<span class="field-label-required" aria-hidden="true">*</span>{/if}
	{@render marks?.()}
	{#if docsId !== undefined}
		<FieldDocsLink id={docsId} fallbackId={docsFallbackId} {label} link={docsLink} title={docsTitle} />
	{/if}
	{@render children?.()}
</div>

<style>
	.field-label-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.field-label-required {
		margin-left: -0.375rem;
		color: var(--color-danger);
	}
</style>
