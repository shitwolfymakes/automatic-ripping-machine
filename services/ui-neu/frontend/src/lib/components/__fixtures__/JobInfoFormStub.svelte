<script lang="ts">
	// Stands in for JobInfoForm: each button reports one kind of saved change.
	let { onsaved }: { onsaved?: (changed: { season: boolean; disc: boolean }) => void } = $props();
</script>

<button type="button" onclick={() => onsaved?.({ season: true, disc: false })}>Saved season</button>
<button type="button" onclick={() => onsaved?.({ season: false, disc: true })}>Saved disc</button>
<button type="button" onclick={() => onsaved?.({ season: false, disc: false })}>Saved other</button>
