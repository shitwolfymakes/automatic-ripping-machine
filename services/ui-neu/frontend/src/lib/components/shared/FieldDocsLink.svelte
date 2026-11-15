<script lang="ts">
	import Glyph from './Glyph.svelte';
	import { docsHref, docsLinkFor, type DocsLink } from '$lib/docs/field-docs';

	// The info "i" that opens the documentation for one field. Renders nothing
	// when the field has no link (an opt-out or an unknown id).
	interface Props {
		// Registry id of the field (config.<KEY>, form.<form>.<field>, ...).
		id: string;
		// Broader registry id used when `id` has no entry of its own.
		fallbackId?: string;
		// The field's visible label, for the accessible name.
		label: string;
		// A link resolved by the caller; takes the place of the registry lookup.
		link?: DocsLink | null;
		// Hover text in place of the default (a HandBrake setting names its key).
		title?: string;
	}

	let { id, fallbackId, label, link, title }: Props = $props();

	const target = $derived(link === undefined ? docsLinkFor(id, fallbackId) : link);
	const external = $derived(target?.type === 'external');
</script>

{#if target}
	<a
		class="field-docs-link"
		href={docsHref(target)}
		target={external ? '_blank' : undefined}
		rel={external ? 'noopener noreferrer' : undefined}
		title={title ?? (external ? 'Open the documentation' : 'Open the ARM help')}
		aria-label={`Docs for ${label}`}
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
