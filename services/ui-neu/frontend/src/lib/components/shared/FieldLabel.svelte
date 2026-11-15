<script lang="ts">
	import type { Snippet } from 'svelte';
	import FieldDocsLink from './FieldDocsLink.svelte';
	import type { DocsLink } from '$lib/docs/field-docs';

	// A field's <label for> with its docs "i" beside it and room for trailing
	// marks (a "Changed" chip, a Reset button). Without `for` (a read-only value,
	// a list with no single control) the name is a plain caption.
	interface Props {
		for?: string;
		label: string;
		// Registry id of the field; without one no docs link is shown.
		docsId?: string;
		docsFallbackId?: string;
		docsLink?: DocsLink | null;
		docsTitle?: string;
		children?: Snippet;
	}

	let { for: htmlFor, label, docsId, docsFallbackId, docsLink, docsTitle, children }: Props = $props();
</script>

<div class="field-label-row">
	{#if htmlFor === undefined}
		<span class="field-label">{label}</span>
	{:else}
		<label class="field-label" for={htmlFor}>{label}</label>
	{/if}
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
</style>
