<script lang="ts">
	import TrackStageRow from '../TrackStageRow.svelte';
	import type { ComponentProps } from 'svelte';

	let props: ComponentProps<typeof TrackStageRow> = $props();
</script>

<table>
	<tbody>
		<TrackStageRow {...props} />
	</tbody>
</table>
