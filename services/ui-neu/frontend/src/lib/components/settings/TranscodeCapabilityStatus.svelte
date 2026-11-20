<script lang="ts">
	// Whether this deployment can run transcode containers at all (set at install
	// time) and, once the GPU list is known, whether encoding falls back to the CPU.
	import StatusField from '$lib/components/shared/StatusField.svelte';
	import StatusStrip from '$lib/components/shared/StatusStrip.svelte';

	let { capable, gpuEnabled }: { capable: boolean; gpuEnabled?: boolean } = $props();
</script>

<div class="stack stack-sm" data-testid="transcode-capability">
	<StatusField
		label="Deployment"
		tone={capable ? 'ok' : 'muted'}
		title={capable ? 'Transcoding supported' : 'Transcoding unsupported'}
	/>
	{#if capable && gpuEnabled === false}
		<StatusStrip tone="muted" title="No GPU enabled" detail="CPU encoding enabled" />
	{/if}
</div>
