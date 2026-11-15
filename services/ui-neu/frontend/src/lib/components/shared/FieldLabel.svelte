<script lang="ts">
	import type { Snippet } from 'svelte';
	import FieldDocsLink from './FieldDocsLink.svelte';
	import type { DocsLink } from '$lib/docs/field-docs';

	// A field's <label for> with its docs "i" beside it and room for trailing
	// marks (a "Changed" chip, a Reset button).
	interface Props {
		for: string;
		label: string;
		// Registry id of the field; without one no docs link is shown.
		docsId?: string;
		docsFallbackId?: string;
		docsLink?: DocsLink | null;
		children?: Snippet;
	}

	let { for: htmlFor, label, docsId, docsFallbackId, docsLink, children }: Props = $props();
</script>

<div class="field-label-row">
	<label class="field-label" for={htmlFor}>{label}</label>
	{#if docsId !== undefined}
		<FieldDocsLink id={docsId} fallbackId={docsFallbackId} {label} link={docsLink} />
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
