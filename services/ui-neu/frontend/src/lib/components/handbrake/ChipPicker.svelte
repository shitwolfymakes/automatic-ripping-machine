<script lang="ts">
	// A list of strings as removable chips plus an add control: a select when
	// the key offers options, a searchable input over `choices` (chips show the
	// choice label; a value no choice carries shows raw), free text otherwise.
	// Emits the whole new list.
	import { choiceLabel, findChoice, type Choice } from '$lib/handbrake/languages';
	interface Props {
		id: string;
		values: string[];
		options: Array<string | number> | null;
		choices?: Choice[] | null;
		disabled?: boolean;
		onchange: (values: string[]) => void;
	}

	let { id, values, options, choices = null, disabled = false, onchange }: Props = $props();

	let draft = $state('');
	function unchosen(list: Array<string | number>): string[] {
		return list.map(String).filter((o) => !values.includes(o));
	}

	function resolve(raw: string): string {
		return choices ? (findChoice(choices, raw)?.value ?? '') : raw.trim();
	}
	function add(raw: string) {
		const value = resolve(raw);
		draft = '';
		if (value !== '' && !values.includes(value)) onchange([...values, value]);
	}
	function remove(value: string) {
		onchange(values.filter((v) => v !== value));
	}
	function onkeydown(e: KeyboardEvent) {
		if (e.key !== 'Enter') return;
		e.preventDefault();
		add(draft);
	}
	function onpick(e: Event) {
		add((e.currentTarget as HTMLSelectElement).value);
	}
</script>

<div class="chip-picker">
	<ul class="chip-picker-chips">
		{#each values as value (value)}
			<li class="chip-picker-chip">
				{choiceLabel(choices, value)}
				<button type="button" aria-label={`Remove ${value}`} {disabled} onclick={() => remove(value)}>x</button>
			</li>
		{/each}
	</ul>
	{#if options}
		<select {id} class="field-control" aria-label="Add value" {disabled} onchange={onpick}>
			<option value="" selected>Add...</option>
			{#each unchosen(options) as choice (choice)}
				<option>{String(choice)}</option>
			{/each}
		</select>
	{:else}
		<div class="chip-picker-add">
			<input
				{id}
				class="field-control"
				aria-label="Add value"
				list={choices ? `${id}-choices` : undefined}
				bind:value={draft}
				{disabled}
				{onkeydown}
			/>
			{#if choices}
				<datalist id={`${id}-choices`}>
					{#each choices.filter((c) => !values.includes(c.value)) as choice (choice.value)}
						<option value={choice.label}></option>
					{/each}
				</datalist>
			{/if}
			<button type="button" class="btn btn-sm" {disabled} onclick={() => add(draft)}>Add</button>
		</div>
	{/if}
</div>

<style>
	.chip-picker-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		margin-bottom: 0.25rem;
		list-style: none;
		padding: 0;
	}
	.chip-picker-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0 0.5rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		font-size: 0.875rem;
	}
	.chip-picker-add {
		display: flex;
		gap: 0.25rem;
	}
</style>
