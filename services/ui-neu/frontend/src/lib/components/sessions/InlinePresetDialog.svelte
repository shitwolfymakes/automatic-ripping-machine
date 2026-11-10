<script lang="ts">
	// The sessions area's stacked preset dialog: a rip or transcode
	// preset form, to create one or edit one, layered above the
	// builder slide-over.
	import RipPresetForm from '$lib/components/RipPresetForm.svelte';
	import TranscodePresetForm from '$lib/components/TranscodePresetForm.svelte';
	import type { RipPresetView, TranscodePresetView } from '$lib/types/api.gen';

	interface Props {
		kind: 'rip' | 'transcode';
		/** The preset to edit, or null to create one. */
		preset: RipPresetView | TranscodePresetView | null;
		onripsaved: (p: RipPresetView) => void;
		ontranscodesaved: (p: TranscodePresetView) => void;
		/** Closes the dialog without saving: the scrim and the form's Cancel. */
		onclose: () => void;
	}
	let { kind, preset, onripsaved, ontranscodesaved, onclose }: Props = $props();

	// Inline dialog label for ARIA
	let inlineDialogLabel = $derived(
		kind === 'rip'
			? preset
				? 'Edit rip preset'
				: 'New rip preset'
			: preset
				? 'Edit transcode preset'
				: 'New transcode preset'
	);
</script>

<!-- Stacked modal: same shape as .modal, but layered above the builder
	 slide-over (z-index bumped in the scoped rule below - the block's own
	 z-index of 50 would sit under the slide-over's 50 in source order). -->
<div class="modal sessions-area-inline-modal">
	<button type="button" class="sessions-area-scrim" aria-label="Close dialog" onclick={onclose}></button>

	<div role="dialog" aria-modal="true" aria-label={inlineDialogLabel} class="modal-panel sessions-area-inline-panel">
		{#if kind === 'rip'}
			<RipPresetForm preset={preset as RipPresetView | null} onsaved={onripsaved} oncancel={onclose} />
		{:else}
			<TranscodePresetForm
				preset={preset as TranscodePresetView | null}
				onsaved={ontranscodesaved}
				oncancel={onclose}
			/>
		{/if}
	</div>
</div>

<style>
	/* the inline create/edit dialog stacks above the builder slide-over
	   (both are z-index: 50 in their block files); bump this one layer
	   higher so it wins the stacking contest the original's z-60/z-70
	   pairing guaranteed explicitly. */
	.sessions-area-inline-modal {
		z-index: 60;
	}
	/* scrim button covers the backdrop box behind the panel, same pattern as
	   ConfirmDialog.svelte - the panel gets its own stacking context via
	   z-index so no click-guard is needed on the panel itself. */
	.sessions-area-scrim {
		position: absolute;
		inset: 0;
		z-index: 0;
		background: transparent;
		border: 0;
		padding: 0;
		cursor: default;
	}
	.sessions-area-inline-panel {
		position: relative;
		z-index: 1;
	}
</style>
