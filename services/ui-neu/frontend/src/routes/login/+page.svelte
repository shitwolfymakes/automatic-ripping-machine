<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { reveal } from '$lib/transitions';
	import { login } from '$lib/api/auth';
	import { applyLogin, isGuest } from '$lib/stores/auth';

	let username = $state('');
	let password = $state('');
	let error = $state('');
	let submitting = $state(false);

	// Whether guest browsing is available: probe one cheap guest-readable GET
	// anonymously. Raw fetch on purpose — the API client would attach the token
	// and route a 401 through the global logout/redirect handler, which must
	// not fire for a probe. 200 = guest access enabled, anything else = hide
	// the Continue-as-Guest button.
	let guestEnabled = $state(false);
	onMount(async () => {
		try {
			const res = await fetch('/api/system/version');
			guestEnabled = res.ok;
		} catch {
			guestEnabled = false;
		}
	});

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
			{submitting ? 'Signing in...' : 'Sign in'}
		</button>
		{#if $isGuest && guestEnabled}
			<button
				type="button"
				onclick={() => goto('/')}
				in:reveal
				class="w-full rounded bg-amber-500 px-4 py-2 font-medium text-white hover:bg-amber-600"
			>
				Continue as Guest
			</button>
		{/if}
	</form>
</div>
