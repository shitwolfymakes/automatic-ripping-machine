<script lang="ts">
	// A value in a facts grid that an admin edits in place: click it, type,
	// Enter saves (Escape cancels, leaving the field saves too). The owner
	// does the save and the reload; this only holds the draft.
	interface Props {
		label: string;
		value: string | null | undefined;
		type?: 'text' | 'number';
		canEdit?: boolean;
		class?: string;
		onsave: (raw: string) => Promise<void> | void;
	}
	let { label, value, type = 'text', canEdit = false, class: className = '', onsave }: Props = $props();

	let editing = $state(false);
	let draft = $state<string | number>('');
	let busy = $state(false);
	let error = $state<string | null>(null);
	let input = $state<HTMLInputElement | undefined>(undefined);

	const shown = $derived(value == null || value === '' ? '-' : String(value));

	function open() {
		if (!canEdit || busy) return;
		draft = value == null ? '' : String(value);
		error = null;
		editing = true;
	}
	$effect(() => {
		if (editing) input?.focus();
	});
	async function save() {
		if (!editing || busy) return;
		// A number input binds a number; the owner always gets the typed text.
		const text = draft == null ? '' : String(draft);
		if (text === (value == null ? '' : String(value))) {
			editing = false;
			return;
		}
		busy = true;
		error = null;
		try {
			await onsave(text);
			editing = false;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Save failed';
		} finally {
			busy = false;
		}
	}
	function cancel() {
		editing = false;
		error = null;
	}
	function onkeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			save();
		} else if (e.key === 'Escape') {
			e.preventDefault();
			cancel();
		}
	}
</script>

{#if editing}
	<input
		bind:this={input}
		bind:value={draft}
		{type}
		aria-label={label}
		class="field-control inline-field-input {className}"
		disabled={busy}
		placeholder="-"
		{onkeydown}
		onblur={save}
	/>
	{#if error}<span class="field-error inline-field-error">{error}</span>{/if}
{:else if canEdit}
	<button type="button" class="inline-field-value {className}" aria-label="Edit {label}" title="Edit" onclick={open}
		>{shown}</button
	>
{:else}
	<span class={className}>{shown}</span>
{/if}

<style>
	.inline-field-value {
		padding: 0 0.25rem;
		margin: 0 -0.25rem;
		border: 1px dashed transparent;
		border-radius: var(--radius-sm);
		background: none;
		font: inherit;
		color: inherit;
		text-align: left;
		cursor: text;
	}
	.inline-field-value:hover,
	.inline-field-value:focus-visible {
		border-color: var(--color-border-strong);
		background: var(--color-primary-tint-1);
		outline: none;
	}
	.inline-field-input {
		min-height: 1.75rem;
		padding: 0.125rem 0.5rem;
		width: 100%;
		max-width: 12rem;
	}
	.inline-field-error {
		display: block;
		margin-top: 0.25rem;
	}
</style>
