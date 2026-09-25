<script lang="ts">
	let {
		checked,
		label,
		onchange,
		disabled = false
	}: { checked: boolean; label: string; onchange?: (next: boolean) => void; disabled?: boolean } = $props();
</script>

<button
	type="button"
	role="switch"
	aria-checked={checked}
	aria-label={label}
	{disabled}
	onclick={(e) => { e.stopPropagation(); onchange?.(!checked); }}
	class="toggle"
>
	<span class="toggle-thumb"></span>
</button>
