<script lang="ts">
	// The identify dialog's fields for a video or data disc (title and year),
	// bound to the dialog's state.
	interface Props {
		/** Disc title. */
		title: string;
		/** Release year, or null when unknown. */
		year: number | null;
		/** Disables every input while the dialog saves. */
		submitting: boolean;
		/** Called on each edit of the title. */
		ontitleinput: () => void;
	}

	let { title = $bindable(), year = $bindable(), submitting, ontitleinput }: Props = $props();
</script>

<div class="mb-3 flex gap-3">
	<label class="field identify-dialog-field-wide">
		<span class="field-label">Title</span>
		<input
			bind:value={title}
			oninput={() => ontitleinput()}
			type="text"
			required
			data-testid="identify-title"
			disabled={submitting}
		/>
	</label>
	<label class="field flex-1">
		<span class="field-label">Year</span>
		<input bind:value={year} type="number" min="1888" max="2100" data-testid="identify-year" disabled={submitting} />
	</label>
</div>

<style>
	.identify-dialog-field-wide {
		flex: 2 1 0%;
	}
</style>
