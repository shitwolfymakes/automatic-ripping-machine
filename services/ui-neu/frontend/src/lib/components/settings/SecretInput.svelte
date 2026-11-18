<script lang="ts">
	// A secret's input, with a button that shows or hides what it holds.
	// A saved secret arrives as the mask: the input shows it empty, with a
	// placeholder saying that a blank keeps it.
	import type { HTMLInputAttributes } from 'svelte/elements';
	import { HIDDEN_SECRET } from '$lib/api/config';
	import Glyph from '$lib/components/shared/Glyph.svelte';

	interface Props extends Omit<HTMLInputAttributes, 'type' | 'value' | 'placeholder' | 'oninput'> {
		/** The secret, bound: the mask while a saved one is kept. */
		value: unknown;
		/** The placeholder while no secret is saved. */
		placeholder?: string;
		/** The reveal button's accessible name. */
		revealLabel: string;
		/** Called after each edit, once `value` holds the typed text. */
		oninput?: () => void;
	}
	let { value = $bindable(), placeholder = '', revealLabel, oninput, ...rest }: Props = $props();

	let reveal = $state(false);
</script>

<input
	{...rest}
	type={reveal ? 'text' : 'password'}
	value={value === HIDDEN_SECRET ? '' : ((value as string | null) ?? '')}
	placeholder={value === HIDDEN_SECRET ? '******** (set, leave blank to keep)' : placeholder}
	oninput={(e) => {
		value = e.currentTarget.value;
		oninput?.();
	}}
/>
<button
	type="button"
	class="btn btn-icon"
	aria-label={revealLabel}
	aria-pressed={reveal}
	onclick={() => (reveal = !reveal)}
>
	<Glyph name={reveal ? 'eye-off' : 'eye'} />
</button>
