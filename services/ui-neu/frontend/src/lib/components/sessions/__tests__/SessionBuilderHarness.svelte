<script lang="ts">
	// SessionBuilder as the session sidebar hosts it: the builder plus the shared
	// footer that submits it by id, fed by the builder's status.
	import type { ComponentProps } from 'svelte';
	import SessionBuilder from '../SessionBuilder.svelte';
	import EditorFormFooter from '../../shared/EditorFormFooter.svelte';
	import { IDLE_STATUS, type EditorStatus } from '../../../ui/editor-status';

	let props: Omit<ComponentProps<typeof SessionBuilder>, 'formId' | 'onstatus'> = $props();

	let status = $state<EditorStatus>(IDLE_STATUS);
</script>

<SessionBuilder {...props} formId="harness-form" onstatus={(s) => (status = s)} />
<EditorFormFooter
	note={status.note}
	readOnly={props.session?.is_builtin ?? false}
	formId="harness-form"
	submitting={status.submitting}
	onclose={() => {}}
/>
