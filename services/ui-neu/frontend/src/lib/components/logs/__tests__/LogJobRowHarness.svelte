<script lang="ts">
	import LogJobRow from '../LogJobRow.svelte';
	import type { ComponentProps } from 'svelte';

	let props: ComponentProps<typeof LogJobRow> = $props();
</script>

<table>
	<tbody>
		<LogJobRow {...props} />
	</tbody>
</table>
