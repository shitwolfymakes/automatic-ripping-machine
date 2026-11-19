<script lang="ts">
	// Whether this deployment can run transcode containers at all, set at install time.
	let { capable }: { capable: boolean } = $props();
</script>

<span class="badge {capable ? 'badge-success' : ''}" data-testid="transcode-capability">
	{capable ? 'Transcoding supported' : 'Transcoding unsupported'}
</span>
