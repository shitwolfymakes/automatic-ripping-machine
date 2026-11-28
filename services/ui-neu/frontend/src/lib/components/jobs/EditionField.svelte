<script lang="ts">
	import InlineField from '$lib/components/shared/InlineField.svelte';
	import { updateTrack } from '$lib/api/jobs';
	import { editionEdit } from '$lib/jobs/edition';

	// The name of one version of the film, edited in place; it becomes {edition?} / {plex_edition?} in the
	// output path when the job keeps more than one version.
	interface Props {
		jobId: string;
		trackId: string;
		edition: string | null | undefined;
		canEdit: boolean;
		onsaved?: () => void;
	}
	let { jobId, trackId, edition, canEdit, onsaved }: Props = $props();

	async function save(raw: string) {
		await updateTrack(jobId, trackId, editionEdit(raw));
		onsaved?.();
	}
</script>

<InlineField label="Edition name" value={edition} {canEdit} onsave={save} />
