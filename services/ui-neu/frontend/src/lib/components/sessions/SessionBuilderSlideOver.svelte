<script lang="ts">
	// The sessions area's builder slide-over: the session builder in a
	// side panel, titled for what it is doing, over a scrim that closes it.
	import SessionBuilder from './SessionBuilder.svelte';
	import CloseButton from '$lib/components/CloseButton.svelte';
	import type { JoinedSession } from './sessionsData.svelte';
	import type { RipPresetView, SessionView, TranscodePresetView } from '$lib/types/api.gen';

	interface Props {
		/** The session to edit or view, or null to create one. */
		session: JoinedSession | null;
		ripPresets: RipPresetView[];
		transcodePresets: TranscodePresetView[];
		oncreaterip: () => void;
		oncreatetranscode: () => void;
		onsaved: (s: SessionView) => void;
		/** Closes the panel without saving: the scrim, the close button and the builder's Cancel. */
		oncancel: () => void;
		preselectRipId?: string;
		preselectTranscodeId?: string;
	}

	let {
		session,
		ripPresets,
		transcodePresets,
		oncreaterip,
		oncreatetranscode,
		onsaved,
		oncancel,
		preselectRipId,
		preselectTranscodeId
	}: Props = $props();
</script>

<div class="slide-over">
	<!-- Backdrop: a button (not a click handler on the flex container),
		 same pattern as ConfirmDialog.svelte - the panel sits in its own
		 stacking context via z-index so it never needs a stopPropagation
		 click guard, which a11y flags on non-interactive elements. -->
	<button type="button" class="sessions-area-scrim" aria-label="Close panel" onclick={oncancel}></button>

	<div class="slide-over-panel sessions-area-slide-over-panel">
		<div class="slide-over-header">
			<h2 class="sessions-area-dialog-title">
				{session?.is_builtin ? 'View session' : session ? 'Edit session' : 'Create a session'}
			</h2>
			<CloseButton onclick={oncancel} />
		</div>

		<div class="sessions-area-builder-body">
			<SessionBuilder
				{session}
				{ripPresets}
				{transcodePresets}
				{oncreaterip}
				{oncreatetranscode}
				{onsaved}
				{oncancel}
				{preselectRipId}
				{preselectTranscodeId}
			/>
		</div>
	</div>
</div>

<style>
	.sessions-area-dialog-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.sessions-area-builder-body {
		flex: 1;
		overflow-y: auto;
		padding: 1.5rem;
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
	.sessions-area-slide-over-panel {
		position: relative;
		z-index: 1;
	}
</style>
