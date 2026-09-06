<script module lang="ts">
	export type { GlyphName } from './glyph-names';
</script>

<script lang="ts">
	import { GLYPH_PATHS, type GlyphName } from './glyph-names';

	interface Props {
		name: GlyphName;
		class?: string;
		label?: string;
	}

	let { name, class: className = '', label }: Props = $props();
	// Default size only when the caller sets none, so an explicit `h-3 w-3`
	// never competes with `h-4 w-4` in the cascade.
	const sizeClass = $derived(/\b[hw]-/.test(className) ? '' : 'h-4 w-4');
</script>

{#if label}
	<svg
		class="shrink-0 {sizeClass} {className}"
		fill="none"
		stroke="currentColor"
		viewBox="0 0 24 24"
		role="img"
		aria-label={label}
	><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={GLYPH_PATHS[name]} /></svg>
{:else}
	<svg
		class="shrink-0 {sizeClass} {className}"
		fill="none"
		stroke="currentColor"
		viewBox="0 0 24 24"
		aria-hidden="true"
	><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={GLYPH_PATHS[name]} /></svg>
{/if}
