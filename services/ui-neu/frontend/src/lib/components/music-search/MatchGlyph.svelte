<script lang="ts">
	// The glyph for one match kind, drawn inside a match cell.
	import type { MatchKind } from '$lib/jobs/track-match';
	import Glyph from '../Glyph.svelte';

	interface Props {
		/** The match kind to draw. */
		kind: MatchKind;
	}
	let { kind }: Props = $props();
</script>

{#if kind === 'match'}
	<Glyph name="check" class="mx-auto h-3.5 w-3.5" />
{:else if kind === 'mismatch'}
	<Glyph name="x" class="mx-auto h-3.5 w-3.5" />
{:else if kind === 'close'}
	~
{:else}
	-
{/if}
