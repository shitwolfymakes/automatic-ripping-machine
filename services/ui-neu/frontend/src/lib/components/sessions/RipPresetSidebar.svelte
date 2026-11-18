<script lang="ts">
	// The rip preset editor on Settings > Sessions: RipPresetForm in an
	// EditorSidebar. Built-in presets open read-only, with a Clone action.
	import EditorSidebar from '$lib/components/EditorSidebar.svelte';
	import EditorFormFooter from '$lib/components/EditorFormFooter.svelte';
	import RipPresetForm from '$lib/components/RipPresetForm.svelte';
	import { IDLE_STATUS, type EditorStatus } from '$lib/components/editorStatus';
	import { usageLabel } from '$lib/handbrake/sidebarModel';
	import type { RipPresetView } from '$lib/types/api.gen';

	const FORM_ID = 'rip-preset-sidebar-form';

	interface Props {
		/** The preset to edit or view, or null to create one. */
		preset: RipPresetView | null;
		readOnly: boolean;
		/** Opened over the session sidebar. */
		stacked?: boolean;
		/** Sessions using the preset, for the footer's usage line. */
		usage?: number;
		/** Makes an editable copy; offered on a read-only preset. */
		onclone?: (p: RipPresetView) => void;
		onsaved: (p: RipPresetView) => void;
		onclose: () => void;
	}

	let { preset, readOnly, stacked = false, usage = 0, onclone, onsaved, onclose }: Props = $props();

	let open = $state(true);
	let status = $state<EditorStatus>(IDLE_STATUS);

	const title = $derived(readOnly ? 'View rip preset' : preset ? 'Edit rip preset' : 'New rip preset');
</script>

<EditorSidebar bind:open {title} width="form" {stacked} {onclose}>
	{#snippet headerActions()}
		{#if readOnly && preset && onclone}
			<button type="button" class="btn btn-sm" onclick={() => onclone(preset)}>Clone</button>
		{/if}
	{/snippet}

	<RipPresetForm {preset} {onsaved} formId={FORM_ID} onstatus={(s) => (status = s)} />

	{#snippet footer()}
		<EditorFormFooter note={usageLabel(usage)} {readOnly} formId={FORM_ID} submitting={status.submitting} {onclose} />
	{/snippet}
</EditorSidebar>
