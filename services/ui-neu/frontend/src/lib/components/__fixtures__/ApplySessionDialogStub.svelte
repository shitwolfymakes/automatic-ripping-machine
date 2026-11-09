<script lang="ts">
	// Stands in for ApplySessionDialog: two buttons call the card's callbacks.
	let { onclose, onapplied }: { onclose: () => void; onapplied: () => void } = $props();
</script>

<div data-testid="apply-session-stub">
	<button type="button" onclick={() => onapplied()}>Stub apply</button>
	<button type="button" onclick={() => onclose()}>Stub close</button>
</div>
