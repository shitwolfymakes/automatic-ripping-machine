<script lang="ts">
	import LogSearchField from '../LogSearchField.svelte';

	// Holds the field's bound values in real $state, as LogView does, so a test
	// can read back what the field wrote.
	let {
		initialText = '',
		initialMatchCase = false,
		matches = 0
	}: { initialText?: string; initialMatchCase?: boolean; matches?: number } = $props();

	let text = $state(initialText);
	let matchCase = $state(initialMatchCase);
	let field = $state<LogSearchField | null>(null);

	export function getText(): string {
		return text;
	}

	export function getMatchCase(): boolean {
		return matchCase;
	}

	export function focusField(): void {
		field?.focus();
	}
</script>

<LogSearchField bind:this={field} bind:text bind:matchCase {matches} />
<output data-testid="bound-text">{text}</output>
<output data-testid="bound-match-case">{matchCase}</output>
