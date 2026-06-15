<script lang="ts">
	import { goto } from '$app/navigation';
	import { login } from '$lib/api/auth';
	import { applyLogin } from '$lib/stores/auth';

	let username = $state('');
	let password = $state('');
	let error = $state('');
	let submitting = $state(false);

	async function onSubmit(e: Event) {
		e.preventDefault();
		if (submitting) return;
		submitting = true;
		error = '';
		try {
			const result = await login(username, password);
			applyLogin(result);
			goto(result.password_must_change ? '/change-password' : '/');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Login failed';
		} finally {
			submitting = false;
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center p-4">
	<form onsubmit={onSubmit} class="w-full max-w-sm space-y-4 rounded-lg border border-primary/20 bg-surface p-6 dark:bg-surface-dark">
		<h1 class="text-lg font-semibold">Sign in to ARM</h1>
		{#if error}
			<p class="rounded bg-red-100 px-3 py-2 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">{error}</p>
		{/if}
		<label class="block text-sm">
			<span class="mb-1 block">Username</span>
			<input bind:value={username} required autocomplete="username" class="w-full rounded border border-primary/20 px-3 py-2 dark:bg-surface-dark" />
		</label>
		<label class="block text-sm">
			<span class="mb-1 block">Password</span>
			<input bind:value={password} type="password" required autocomplete="current-password" class="w-full rounded border border-primary/20 px-3 py-2 dark:bg-surface-dark" />
		</label>
		<button type="submit" disabled={submitting} class="w-full rounded bg-primary px-4 py-2 font-medium text-white disabled:opacity-60">
			{submitting ? 'Signing in…' : 'Sign in'}
		</button>
	</form>
</div>
