<script lang="ts">
	let {
		checked,
		label,
		onchange
	}: { checked: boolean; label: string; onchange?: (next: boolean) => void } = $props();
</script>

<button
	type="button"
	role="switch"
	aria-checked={checked}
	aria-label={label}
	onclick={(e) => { e.stopPropagation(); onchange?.(!checked); }}
	class="toggle"
>
	<span class="toggle-thumb"></span>
</button>
