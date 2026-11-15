<script lang="ts">
	// The sessions area's session editor: the session builder in an
	// EditorSidebar, titled for what it is doing.
	import EditorSidebar from '$lib/components/EditorSidebar.svelte';
	import EditorFormFooter from '$lib/components/EditorFormFooter.svelte';
	import { IDLE_STATUS, type EditorStatus } from '$lib/components/editorStatus';
	import SessionBuilder from './SessionBuilder.svelte';
	import type { JoinedSession } from './sessionsData.svelte';
	import type { RipPresetView, SessionView, TranscodePresetView } from '$lib/types/api.gen';

	const FORM_ID = 'session-builder-form';

	interface Props {
		/** The session to edit or view, or null to create one. */
		session: JoinedSession | null;
		ripPresets: RipPresetView[];
		transcodePresets: TranscodePresetView[];
		oncreaterip: () => void;
		oncreatetranscode: () => void;
		onsaved: (s: SessionView) => void;
		/** Closes the panel without saving: the scrim, Close and the footer's Cancel. */
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

	let open = $state(true);
	let status = $state<EditorStatus>(IDLE_STATUS);

	const readOnly = $derived(session?.is_builtin ?? false);
	const title = $derived(readOnly ? 'View session' : session ? 'Edit session' : 'New session');
</script>

<EditorSidebar bind:open {title} width="form" onclose={oncancel}>
	<SessionBuilder
		{session}
		{ripPresets}
		{transcodePresets}
		{oncreaterip}
		{oncreatetranscode}
		{onsaved}
		{preselectRipId}
		{preselectTranscodeId}
		formId={FORM_ID}
		onstatus={(s) => (status = s)}
	/>

	{#snippet footer()}
		<EditorFormFooter
			note={status.note}
			{readOnly}
			formId={FORM_ID}
			submitting={status.submitting}
			onclose={oncancel}
		/>
	{/snippet}
</EditorSidebar>
