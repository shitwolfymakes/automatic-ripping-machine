<script lang="ts">
	let {
		id,
		checked,
		label,
		onchange,
		disabled = false
	}: {
		// For a <label for> beside the switch.
		id?: string;
		checked: boolean;
		label: string;
		onchange?: (next: boolean) => void;
		disabled?: boolean;
	} = $props();
</script>

<button
	{id}
	type="button"
	role="switch"
	aria-checked={checked}
	aria-label={label}
	{disabled}
	onclick={(e) => {
		e.stopPropagation();
		onchange?.(!checked);
	}}
	class="toggle"
>
	<span class="toggle-thumb"></span>
</button>
