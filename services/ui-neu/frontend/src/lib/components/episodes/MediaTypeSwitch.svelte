<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import { setJobMediaType } from '$lib/api/jobs';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';

	type MediaType = 'movie' | 'tv';

	interface Props {
		job: JobView;
		// Tracks whose episode number or role the user set by hand; switching to
		// Movie drops that work, so it asks first.
		handSetCount: number;
		onchanged: (type: MediaType) => void;
	}
	let { job, handSetCount, onchanged }: Props = $props();

	const OPTIONS: { value: MediaType; label: string }[] = [
		{ value: 'movie', label: 'Movie' },
		{ value: 'tv', label: 'TV' }
	];

	let confirmOpen = $state(false);
	let saving = $state(false);
	let error = $state<string | null>(null);
	const current = $derived<MediaType>(job.media_type === 'tv' ? 'tv' : 'movie');
	const confirmMessage = $derived(
		`${handSetCount === 1 ? '1 track has' : `${handSetCount} tracks have`} episodes you set by hand. Switch to Movie anyway?`
	);

	async function apply(type: MediaType) {
		confirmOpen = false;
		saving = true;
		error = null;
		try {
			await setJobMediaType(job.id, type);
			onchanged(type);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not change the type';
		} finally {
			saving = false;
		}
	}

	function choose(type: MediaType) {
		if (type === current || saving) return;
		if (type === 'movie' && handSetCount > 0) confirmOpen = true;
		else apply(type);
	}
</script>

<div class="media-type-switch">
	<div class="media-type-switch-group" role="radiogroup" aria-label="Media type">
		<span class="media-type-switch-label" aria-hidden="true">Type</span>
		{#each OPTIONS as opt (opt.value)}
			<button
				type="button"
				role="radio"
				class="media-type-switch-option"
				aria-checked={current === opt.value}
				disabled={saving}
				onclick={() => choose(opt.value)}>{opt.label}</button
			>
		{/each}
	</div>
	{#if error}
		<span class="media-type-switch-error" role="alert">{error}</span>
	{/if}
</div>
<ConfirmDialog
	open={confirmOpen}
	title="Switch to Movie?"
	message={confirmMessage}
	confirmLabel="Switch to Movie"
	variant="primary"
	onconfirm={() => apply('movie')}
	oncancel={() => (confirmOpen = false)}
/>

<style>
	.media-type-switch {
		display: inline-flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	/* One contained segmented control sized like the header's buttons: no
	   block covers this shape (tabs-pills renders loose pills with no shared
	   frame). The "Type" caption sits inside the frame so label and options
	   read as one control. */
	.media-type-switch-group {
		display: inline-flex;
		align-items: stretch;
		min-height: var(--control-h);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		overflow: hidden;
		background: var(--color-surface);
	}
	.media-type-switch-label {
		display: inline-flex;
		align-items: center;
		padding: 0 0.625rem;
		border-right: 1px solid var(--color-border);
		font-size: 0.6875rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--color-text-muted);
	}
	.media-type-switch-option {
		padding: 0 0.875rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--color-text-muted);
		cursor: pointer;
		transition:
			background-color var(--motion-fast) var(--ease),
			color var(--motion-fast) var(--ease);
	}
	.media-type-switch-option + .media-type-switch-option {
		border-left: 1px solid var(--color-border);
	}
	.media-type-switch-option:hover:not(:disabled) {
		color: var(--color-text);
	}
	.media-type-switch-option[aria-checked='true'] {
		background: var(--color-primary);
		color: var(--color-on-primary);
	}
	.media-type-switch-option:disabled {
		cursor: default;
	}
	.media-type-switch-error {
		font-size: 0.75rem;
		color: var(--color-danger);
	}
</style>
