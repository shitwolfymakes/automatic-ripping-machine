<script lang="ts">
	// The footer of an EditorSidebar that hosts a form: a usage line, Cancel
	// (Close when read-only) and a Save that submits the form by id. Save stays
	// clickable with invalid input (the form marks and focuses what is wrong);
	// only a save in flight disables it.
	interface Props {
		/** The usage line on the left. */
		note: string;
		readOnly: boolean;
		/** Id of the hosted form the Save button submits. */
		formId: string;
		submitting: boolean;
		onclose: () => void;
	}

	let { note, readOnly, formId, submitting, onclose }: Props = $props();
</script>

<div class="editor-form-footer">
	<span class="editor-form-footer-note">{note}</span>
	<button type="button" class="btn btn-ghost" disabled={submitting} onclick={onclose}>
		{readOnly ? 'Close' : 'Cancel'}
	</button>
	{#if !readOnly}
		<button type="submit" form={formId} class="btn btn-primary" disabled={submitting}>
			{submitting ? 'Saving...' : 'Save'}
		</button>
	{/if}
</div>

<style>
	.editor-form-footer {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 0.75rem;
	}
	.editor-form-footer-note {
		margin-right: auto;
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
</style>
