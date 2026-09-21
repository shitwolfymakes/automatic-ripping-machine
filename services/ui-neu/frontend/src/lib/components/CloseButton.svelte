<script lang="ts">
	import Glyph from './Glyph.svelte';

	interface Props {
		onclick: () => void;
		label?: string;
		class?: string;
	}

	let { onclick, label = 'Close', class: className = '' }: Props = $props();
</script>

<button
	type="button"
	aria-label={label}
	{onclick}
	class="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300 {className}"
>
	<Glyph name="x" />
</button>
