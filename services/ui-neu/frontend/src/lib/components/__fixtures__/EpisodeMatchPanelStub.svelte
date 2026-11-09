<script lang="ts">
	// Stands in for EpisodeMatchPanel: one button reports a change in the panel.
	let { onchanged }: { onchanged: () => void } = $props();
</script>

<button type="button" onclick={() => onchanged()}>Stub panel changed</button>
