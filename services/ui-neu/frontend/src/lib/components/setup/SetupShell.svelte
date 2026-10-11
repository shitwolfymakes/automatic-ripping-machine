<script lang="ts">
	import type { Snippet } from 'svelte';
	import { goto } from '$app/navigation';
	import { theme, toggleTheme } from '$lib/stores/theme';
	import Glyph from '$lib/components/Glyph.svelte';
	import { finishLater } from '$lib/stores/setup.svelte';

	// The walkthrough's focused shell: no sidebar, header status strip or
	// resource footer (they point at things that aren't set up yet).
	let {
		stepper,
		footer,
		children,
		showFinishLater = true
	}: { stepper: Snippet; footer: Snippet; children: Snippet; showFinishLater?: boolean } = $props();

	let deferring = $state(false);
	let deferError = $state<string | null>(null);

	// Finish later is recorded server-wide, so wait for it: leaving before the
	// server agrees would just bounce this browser back to /setup.
	async function later() {
		deferring = true;
		deferError = null;
		try {
			await finishLater();
			goto('/');
		} catch (e) {
			deferError = e instanceof Error ? e.message : 'Could not save Finish later.';
		} finally {
			deferring = false;
		}
	}
</script>

<div class="setup-shell">
	<header class="setup-shell-top">
		<div class="setup-shell-brand">
			<img src="/img/arm-logo-black.png" alt="" class="setup-shell-logo setup-shell-logo-light" />
			<img src="/img/arm-logo-white.png" alt="" class="setup-shell-logo setup-shell-logo-dark" />
			<span class="setup-shell-name">Set up ARM</span>
		</div>
		<div class="setup-shell-tools">
			{#if showFinishLater}
				<button type="button" class="btn btn-link" onclick={later} disabled={deferring}>Finish later</button>
			{/if}
			<button
				type="button"
				class="btn btn-icon"
				onclick={toggleTheme}
				aria-label={$theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
			>
				<Glyph name={$theme === 'dark' ? 'sun' : 'moon'} class="h-5 w-5" />
			</button>
		</div>
	</header>

	{#if deferError}
		<div class="alert alert-danger setup-shell-alert" role="alert">
			<p class="alert-title">Couldn't save Finish later</p>
			<p class="alert-body">{deferError}</p>
		</div>
	{/if}

	<div class="setup-shell-body">
		<aside class="setup-shell-steps">{@render stepper()}</aside>
		<main class="setup-shell-main">{@render children()}</main>
	</div>

	{@render footer()}
</div>

<style>
	.setup-shell-alert {
		margin: 0.75rem 1rem 0;
	}
	.setup-shell {
		display: flex;
		min-height: 100vh;
		flex-direction: column;
		background: var(--color-page);
		color: var(--color-text);
	}
	.setup-shell-top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-surface);
		padding: 0.625rem 1rem;
	}
	.setup-shell-brand {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	.setup-shell-logo {
		width: 2.25rem;
		height: 2.25rem;
	}
	.setup-shell-logo-dark {
		display: none;
	}
	/* :global: .dark is the app-level scheme class on <html>, outside this component */
	:global(.dark) .setup-shell-logo-light {
		display: none;
	}
	/* :global: .dark is the app-level scheme class on <html>, outside this component */
	:global(.dark) .setup-shell-logo-dark {
		display: block;
	}
	.setup-shell-name {
		font-size: 1.0625rem;
		font-weight: 700;
	}
	.setup-shell-tools {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.setup-shell-body {
		display: grid;
		align-content: start;
		flex: 1 1 auto;
		gap: 1.5rem;
		width: 100%;
		max-width: 44rem;
		margin: 0 auto;
		padding: 1.25rem 1rem 2rem;
	}
	.setup-shell-main {
		min-width: 0;
	}
	/* inline text links inside steps (buttons styled as links keep their own look) */
	.setup-shell-main :global(a:not(.btn)) {
		color: var(--color-primary-text);
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	@media (min-width: 900px) {
		.setup-shell-body {
			grid-template-columns: 18rem minmax(0, 44rem);
			gap: 3rem;
			max-width: 72rem;
			padding: 2.5rem 1.5rem 3rem;
		}
		.setup-shell-steps {
			position: sticky;
			top: 1.5rem;
			align-self: start;
		}
	}
</style>
