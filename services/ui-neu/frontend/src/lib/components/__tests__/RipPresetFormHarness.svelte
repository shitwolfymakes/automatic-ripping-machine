<script lang="ts">
	// RipPresetForm as the rip sidebar hosts it: the form plus the shared footer
	// that submits it by id, fed by the form's status.
	import RipPresetForm from '../RipPresetForm.svelte';
	import EditorFormFooter from '../EditorFormFooter.svelte';
	import { IDLE_STATUS, type EditorStatus } from '../editor-status';
	import type { RipPresetView } from '$lib/types/api.gen';

	let { preset = null, onsaved }: { preset?: RipPresetView | null; onsaved: (p: RipPresetView) => void } = $props();

	let status = $state<EditorStatus>(IDLE_STATUS);
</script>

<RipPresetForm {preset} {onsaved} formId="harness-form" onstatus={(s) => (status = s)} />
<EditorFormFooter
	note={status.note}
	readOnly={preset?.is_builtin ?? false}
	formId="harness-form"
	submitting={status.submitting}
	onclose={() => {}}
/>
