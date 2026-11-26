<script lang="ts">
	import IdentifyCdForm from '../IdentifyCdForm.svelte';

	// Holds the form's bound values in real $state, as IdentifyDialog does, so a
	// test can read back what the form wrote.
	let { scanTrackCount, submitting = false }: { scanTrackCount: number; submitting?: boolean } = $props();

	let album = $state('');
	let year = $state<number | null>(null);
	let artist = $state('');
	let trackTitles = $state<string[]>(Array.from({ length: scanTrackCount }, () => ''));

	export function getValues(): { album: string; year: number | null; artist: string; trackTitles: string[] } {
		return $state.snapshot({ album, year, artist, trackTitles });
	}
</script>

<IdentifyCdForm bind:album bind:year bind:artist bind:trackTitles {scanTrackCount} {submitting} />
