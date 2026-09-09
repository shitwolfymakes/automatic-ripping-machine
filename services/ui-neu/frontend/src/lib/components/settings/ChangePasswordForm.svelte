<script lang="ts">
	import { reveal } from '$lib/transitions';
	import { changePassword } from '$lib/api/auth';

	let { onsuccess }: { onsuccess: () => void } = $props();

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
			onsuccess();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Password change failed';
		} finally {
			submitting = false;
		}
	}
</script>

<form onsubmit={onSubmit} class="panel change-password-form stack">
	<!-- Title lives in the route page -->

	{#if error}
		<p in:reveal class="alert alert-danger">{error}</p>
	{/if}
	<label class="field">
		<span class="field-label">Current password</span>
		<input bind:value={current} type="password" required autocomplete="current-password" />
	</label>
	<label class="field">
		<span class="field-label">New password</span>
		<input bind:value={next} type="password" required autocomplete="new-password" />
	</label>
	<label class="field">
		<span class="field-label">Confirm new password</span>
		<input bind:value={confirm} type="password" required autocomplete="new-password" />
	</label>
	<button type="submit" disabled={submitting} class="btn btn-primary change-password-form-submit">
		{submitting ? 'Saving...' : 'Set new password'}
	</button>
</form>

<style>
	/* the form is capped to a comfortable reading width and its own vertical
	   rhythm (space-y-4 = 1rem) rather than the wider panel default. */
	.change-password-form { width: 100%; max-width: 24rem; gap: 1rem; }
	.change-password-form-submit { width: 100%; }
</style>
