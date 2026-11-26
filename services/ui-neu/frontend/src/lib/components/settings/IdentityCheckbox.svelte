<script lang="ts">
	import FieldLabel from '$lib/components/shared/FieldLabel.svelte';

	// One of the Identity card's checkbox options, labelled, with the docs link
	// for its setting, and described by the help text the card draws for it.
	let {
		label,
		docsId,
		describedby,
		checked,
		disabled,
		onchange
	}: {
		label: string;
		// Registry id of the setting the box writes (config.<key>).
		docsId: string;
		describedby: string;
		checked: boolean;
		disabled: boolean;
		onchange: (checked: boolean) => void;
	} = $props();

	const id = $props.id();
</script>

<div class="field field-row">
	<input
		{id}
		type="checkbox"
		aria-label={label}
		aria-describedby={describedby}
		{checked}
		{disabled}
		onchange={(e) => onchange((e.currentTarget as HTMLInputElement).checked)}
	/>
	<FieldLabel for={id} {label} {docsId} />
</div>
