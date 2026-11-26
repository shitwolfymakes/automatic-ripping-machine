<script lang="ts">
	import Glyph from './Glyph.svelte';
	import { docsHref, docsLinkFor, docsTitle, type DocsLink } from '$lib/docs/field-docs';

	// The info "i" that opens the documentation for one field in a new tab, so a
	// half-filled form stays open (the UI has no unsaved-changes guard). Renders
	// nothing when the field has no link (an opt-out or an unknown id).
	interface Props {
		// Registry id of the field (config.<KEY>, form.<form>.<field>, ...).
		id: string;
		// Broader registry id used when `id` has no entry of its own.
		fallbackId?: string;
		// The field's bare label (no "*", units or "(optional)"), for the accessible name.
		label: string;
		// A link resolved by the caller; takes the place of the registry lookup.
		link?: DocsLink | null;
		// Hover text in place of the default (a HandBrake setting names its key).
		title?: string;
	}

	let { id, fallbackId, label, link, title }: Props = $props();

	const target = $derived(link === undefined ? docsLinkFor(id, fallbackId) : link);
</script>

{#if target}
	<a
		class="field-docs-link"
		href={docsHref(target)}
		target="_blank"
		rel="noopener noreferrer"
		title={title ?? docsTitle(target)}
		aria-label={`Docs for ${label} (opens in a new tab)`}
		data-field-id={id}
	>
		<Glyph name="info" class="h-3 w-3" />
	</a>
{/if}

<style>
	.field-docs-link {
		display: inline-flex;
		color: var(--color-text-faint);
	}
	.field-docs-link:hover {
		color: var(--color-text);
	}
</style>
