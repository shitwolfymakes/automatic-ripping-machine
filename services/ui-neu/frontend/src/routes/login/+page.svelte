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

<div class="login-page">
	<form onsubmit={onSubmit} class="panel stack login-page-form">
		<h1 class="login-page-title">Sign in to ARM</h1>
		{#if error}
			<p class="alert alert-danger">{error}</p>
		{/if}
		<label class="field">
			<span class="field-label">Username</span>
			<input bind:value={username} type="text" name="username" required autocomplete="username" />
		</label>
		<label class="field">
			<span class="field-label">Password</span>
			<input bind:value={password} type="password" name="password" required autocomplete="current-password" />
		</label>
		<button type="submit" disabled={submitting} class="btn btn-primary login-page-submit">
			{submitting ? 'Signing in...' : 'Sign in'}
		</button>
		{#if $isGuest && guestEnabled}
			<button
				type="button"
				onclick={() => goto('/')}
				in:reveal
				class="btn btn-warning login-page-guest"
			>
				Continue as Guest
			</button>
		{/if}
	</form>
</div>

<style>
	/* full-viewport centering wrapper; not a block, this page's own shell */
	.login-page { display: flex; min-height: 100vh; align-items: center; justify-content: center; padding: 1rem; }
	/* original was p-6 (1.5rem), not panel's own 1rem default */
	.login-page-form { width: 100%; max-width: 24rem; gap: 1rem; padding: 1.5rem; }
	.login-page-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	/* the original inputs had no background utility at all (transparent,
	   inheriting the panel's own surface colour, since text-sm was inherited
	   from the wrapping <label> so field's own default text-sm sizing
	   already matches) and a lighter border (border-primary/20 =
	   --color-border, not field's own --color-border-strong default) */
	.login-page-form input { border-color: var(--color-border); background: transparent; }
	/* the buttons sit OUTSIDE the text-sm label wrapper and carried no
	   text-size utility of their own, so they render at the ambient body
	   size (1rem/1.5rem, confirmed live), not .btn's own text-sm default -
	   height 40px vs .btn's 36px */
	.login-page-submit, .login-page-guest { font-size: 1rem; line-height: 1.5rem; }
	/* original had no border/ring class at all; .btn-primary's own border
	   is invisible (same colour as the fill) but still occupies 2px of
	   layout height without this - measured 2px taller than baseline */
	.login-page-submit { width: 100%; border: 0; }
	/* the original Continue-as-Guest button was a SOLID filled amber pill
	   (bg-amber-500 text-white), not btn-warning's outlined/soft look - the
	   button's own fill/text colours are restated on top of the modifier for
	   its distinct call-to-action tone; btn-warning still supplies the base
	   box model (border/radius/height) and border:0 removes its outline */
	.login-page-guest { width: 100%; border: 0; background: var(--color-warning); color: var(--color-on-primary); }
	/* darkens on hover like the original's bg-amber-500 -> hover:bg-amber-600;
	   no darker warning token exists, so filter substitutes for a literal
	   colour (the lint bans raw colour keywords, even inside color-mix) */
	.login-page-guest:hover { filter: brightness(0.9); }
</style>
