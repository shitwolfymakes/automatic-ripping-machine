<script lang="ts">
	import IdentifyVideoForm from '../IdentifyVideoForm.svelte';

	// Holds the form's bound values in real $state, as IdentifyDialog does, so a
	// test can read back what the form wrote.
	let { submitting = false, ontitleinput }: { submitting?: boolean; ontitleinput: () => void } = $props();

	let title = $state('');
	let year = $state<number | null>(null);

	export function getValues(): { title: string; year: number | null } {
		return $state.snapshot({ title, year });
	}
</script>

<IdentifyVideoForm bind:title bind:year {submitting} {ontitleinput} />
