<script lang="ts">
	// A settings card's feedback line, green for a success and red for an error.
	import { reveal } from '$lib/transitions';
	import type { Feedback } from '../../stores/timed-feedback.svelte';

	let { feedback }: { feedback: Feedback | null } = $props();
</script>

{#if feedback}
	<p in:reveal class="alert {feedback.type === 'success' ? 'alert-success' : 'alert-danger'} mb-3">
		{feedback.message}
	</p>
{/if}
