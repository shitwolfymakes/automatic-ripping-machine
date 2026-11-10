<script lang="ts">
	// One of the Identity card's checkbox options, labelled, and described by
	// the help text the card draws for it.
	let {
		label,
		describedby,
		checked,
		disabled,
		onchange
	}: {
		label: string;
		describedby: string;
		checked: boolean;
		disabled: boolean;
		onchange: (checked: boolean) => void;
	} = $props();
</script>

<label class="field field-row">
	<input
		type="checkbox"
		aria-label={label}
		aria-describedby={describedby}
		{checked}
		{disabled}
		onchange={(e) => onchange((e.currentTarget as HTMLInputElement).checked)}
	/>
	<span class="field-label">{label}</span>
</label>
