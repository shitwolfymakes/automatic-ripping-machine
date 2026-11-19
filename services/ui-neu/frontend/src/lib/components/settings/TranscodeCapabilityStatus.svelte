<script lang="ts">
	// Whether this deployment can run transcode containers at all, set at install time.
	import StatusField from '$lib/components/StatusField.svelte';

	let { capable }: { capable: boolean } = $props();
</script>

<div data-testid="transcode-capability">
	<StatusField
		label="Deployment"
		tone={capable ? 'ok' : 'muted'}
		title={capable ? 'Transcoding supported' : 'Transcoding unsupported'}
	/>
</div>
