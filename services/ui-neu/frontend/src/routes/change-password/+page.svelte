<script lang="ts">
	import { goto } from '$app/navigation';
	import { fade } from 'svelte/transition';
	import { fadeIn } from '$lib/transitions';
	import { changePassword } from '$lib/api/auth';
	import { clearPasswordMustChange } from '$lib/stores/auth';

	let current = $state('');
	let next = $state('');
	let confirm = $state('');
	let error = $state('');
	let submitting = $state(false);

	async function onSubmit(e: Event) {
		e.preventDefault();
		if (submitting) return;
		error = '';
		if (next === current) {
			error = 'New password must differ from the current password';
			return;
		}
		if (next.length < 8) {
			error = 'New password must be at least 8 characters';
			return;
		}
		if (next !== confirm) {
			error = 'Passwords do not match';
			return;
		}
		submitting = true;
		try {
			await changePassword(current, next);
			clearPasswordMustChange();
			goto('/');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Password change failed';
		} finally {
			submitting = false;
		}
	}
</script>

<div in:fade={fadeIn} class="flex min-h-screen items-center justify-center p-4">
	<form onsubmit={onSubmit} class="w-full max-w-sm space-y-4 rounded-lg border border-primary/20 bg-surface p-6 dark:bg-surface-dark">
		<h1 class="text-lg font-semibold">Change your password</h1>
		<p class="text-sm text-gray-600 dark:text-gray-300">You must set a new password before continuing.</p>
		{#if error}
			<p class="rounded bg-red-100 px-3 py-2 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">{error}</p>
		{/if}
		<label class="block text-sm">
			<span class="mb-1 block">Current password</span>
			<input bind:value={current} type="password" required autocomplete="current-password" class="w-full rounded border border-primary/20 px-3 py-2 dark:bg-surface-dark" />
		</label>
		<label class="block text-sm">
			<span class="mb-1 block">New password</span>
			<input bind:value={next} type="password" required autocomplete="new-password" class="w-full rounded border border-primary/20 px-3 py-2 dark:bg-surface-dark" />
		</label>
		<label class="block text-sm">
			<span class="mb-1 block">Confirm new password</span>
			<input bind:value={confirm} type="password" required autocomplete="new-password" class="w-full rounded border border-primary/20 px-3 py-2 dark:bg-surface-dark" />
		</label>
		<button type="submit" disabled={submitting} class="w-full rounded bg-primary px-4 py-2 font-medium text-white disabled:opacity-60">
			{submitting ? 'Saving...' : 'Set new password'}
		</button>
	</form>
</div>
