<script lang="ts">
	import Glyph from './Glyph.svelte';

	interface Props {
		onclick: () => void;
		label?: string;
		class?: string;
	}

	let { onclick, label = 'Close', class: className = '' }: Props = $props();
</script>

<button type="button" aria-label={label} {onclick} class="btn btn-icon {className}">
	<Glyph name="x" />
</button>
