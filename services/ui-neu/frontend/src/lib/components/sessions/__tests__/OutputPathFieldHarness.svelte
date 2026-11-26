<script lang="ts">
	import OutputPathField from '../OutputPathField.svelte';

	// Holds has_transcode_preset in its own $state, as the session builder
	// does, so a test can change it without touching the other props.
	let { value }: { value: string } = $props();

	let hasTranscodePreset = $state(false);

	export function setHasTranscodePreset(next: boolean): void {
		hasTranscodePreset = next;
	}
</script>

<OutputPathField {value} mediaType="movie" onchange={() => {}} has_transcode_preset={hasTranscodePreset} />
