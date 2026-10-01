<script lang="ts">
	import { toasts, dismissToast, type ToastTone } from '$lib/stores/toast.svelte';
	import CloseButton from './CloseButton.svelte';

	function toneClass(tone: ToastTone): string {
		if (tone === 'success') return 'toast-success';
		if (tone === 'error') return 'toast-danger';
		return 'toast-info';
	}
</script>

<div class="toast-host fixed bottom-6 right-6 flex flex-col gap-2">
	{#each toasts.value as t (t.id)}
		<div class="toast {toneClass(t.tone)} toast-host-item" role="status">
			<div class="flex-1">
				<p class="toast-title">{t.title}</p>
				{#if t.body}<p class="toast-body">{t.body}</p>{/if}
				{#if t.link}
					<a href={t.link.href} class="btn btn-link toast-host-link">{t.link.label}</a>
				{/if}
			</div>
			<CloseButton onclick={() => dismissToast(t.id)} label="Dismiss notification" />
		</div>
	{/each}
</div>

<style>
	.toast-host {
		z-index: 50;
		pointer-events: none;
	}
	.toast-host-item {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		min-width: 280px;
		max-width: 420px;
		pointer-events: auto;
	}
	/* .btn-link inherits .btn's own 0.875rem - restate at toast-body's 0.75rem
	   so the link reads as part of this toast's text, not a full-size action,
	   and sits snug under the body line. */
	.toast-host-link {
		margin-top: 0.25rem;
		font-size: 0.75rem;
		line-height: calc(1 / 0.75);
	}
</style>
