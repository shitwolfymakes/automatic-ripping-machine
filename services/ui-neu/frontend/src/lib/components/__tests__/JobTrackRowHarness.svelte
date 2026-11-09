<script lang="ts">
	import JobTrackRow from '../JobTrackRow.svelte';
	import type { ComponentProps } from 'svelte';

	let props: ComponentProps<typeof JobTrackRow> = $props();
</script>

<table>
	<tbody>
		<JobTrackRow {...props} />
	</tbody>
</table>
