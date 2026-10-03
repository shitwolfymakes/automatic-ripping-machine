<script lang="ts">
	interface Props {
		open: boolean;
		title: string;
		message: string;
		confirmLabel?: string;
		variant?: 'danger' | 'primary';
		onconfirm: () => void;
		oncancel: () => void;
	}

	let {
		open,
		title,
		message,
		confirmLabel = 'Confirm',
		variant = 'primary',
		onconfirm,
		oncancel
	}: Props = $props();

	let confirmClasses = $derived(
		variant === 'danger'
			? 'btn-danger'
			: 'btn-primary'
	);

	$effect(() => {
		if (!open) return;
		const onKeyDown = (e: KeyboardEvent) => {
			if (e.key === 'Escape') {
				oncancel();
			}
		};
		window.addEventListener('keydown', onKeyDown);
		return () => window.removeEventListener('keydown', onKeyDown);
	});
</script>

{#if open}
	<div class="modal">
		<!-- Backdrop -->
		<button
			type="button"
			class="confirm-dialog-scrim absolute inset-0"
			aria-label="Close dialog"
			onclick={oncancel}
		></button>

		<!-- Dialog -->
		<div class="modal-panel confirm-dialog-panel relative" data-dialog role="dialog" aria-modal="true" aria-labelledby="dialog-title">
			<h3 id="dialog-title" class="modal-title">{title}</h3>
			<p class="modal-body">{message}</p>
			<div class="modal-actions">
				<button
					type="button"
					onclick={oncancel}
					class="btn btn-ghost"
				>
					Cancel
				</button>
				<button
					type="button"
					onclick={onconfirm}
					class="btn {confirmClasses}"
				>
					{confirmLabel}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	/* modal.css's .modal is the backdrop+centring layer already; the scrim
	   button just needs to sit above it and below the panel (z-index: 0 is
	   the modal's own stacking context, so 'relative' on both is enough - no
	   extra z-index needed). */
	.confirm-dialog-scrim {
		z-index: 0;
	}
	.confirm-dialog-panel {
		z-index: 1;
	}
</style>
