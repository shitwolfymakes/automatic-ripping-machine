<script lang="ts">
	import { goto } from '$app/navigation';
	import { theme, toggleTheme } from '$lib/stores/theme';
	import { schemeLocksMode } from '$lib/stores/color-scheme';
	import { dashboard } from '$lib/stores/dashboard';
	import { setRippingEnabled } from '$lib/api/config';
	import { isoPickerMode, showIsoPicker } from '$lib/stores/iso-picker';
	import Glyph from '$lib/components/shared/Glyph.svelte';
	import Flyout from '$lib/components/shared/Flyout.svelte';
	import FlyoutItem from '$lib/components/shared/FlyoutItem.svelte';
	import FlyoutDivider from '$lib/components/shared/FlyoutDivider.svelte';
	import { logoutLocal, isGuest, isAdmin } from '$lib/stores/auth';
	import { logout as apiLogout } from '$lib/api/auth';

	let togglingPause = $state(false);

	function ripFromIso() {
		isoPickerMode.set('iso');
		showIsoPicker.set(true);
	}

	function ripFromFolder() {
		isoPickerMode.set('folder');
		showIsoPicker.set(true);
	}

	function openSettings() {
		goto('/settings');
	}

	// Deliberate sign-out: best-effort server-side logout, then drop the local
	// session and land on the dashboard. Landing tokenless is a valid guest
	// browsing state — if guest access is disabled, the next request's 401
	// will route to /login on its own.
	async function handleSignOut(): Promise<void> {
		try {
			await apiLogout();
		} catch {
			/* ignore */
		}
		logoutLocal();
		goto('/');
	}

	async function toggleRipping() {
		if (togglingPause) return;
		togglingPause = true;
		const newValue = !$dashboard.ripping_enabled;
		dashboard.update((d) => ({ ...d, ripping_enabled: newValue }));
		try {
			await setRippingEnabled(newValue);
		} catch {
			// Revert on failure — next poll will also reconcile
			dashboard.update((d) => ({ ...d, ripping_enabled: !newValue }));
		} finally {
			togglingPause = false;
		}
	}
</script>

<div class="flex items-center gap-4 ml-auto">
	<!-- Auto-Start toggle -->
	{#if !$isGuest && $dashboard.db_available}
		<button
			type="button"
			role="switch"
			aria-checked={$dashboard.ripping_enabled}
			onclick={toggleRipping}
			disabled={togglingPause}
			class="btn layout-autostart"
			data-active={$dashboard.ripping_enabled}
		>
			<span class="toggle" aria-hidden="true">
				<span class="toggle-thumb"></span>
			</span>
			{$dashboard.ripping_enabled ? 'Auto-Start' : 'Paused'}
		</button>
	{/if}
	<!-- Quick actions menu -->
	{#if !$isGuest}
		<Flyout align="right" width="w-52" label="Quick actions">
			{#snippet trigger({ toggle })}
				<button type="button" onclick={toggle} class="btn btn-icon layout-header-icon" title="Quick actions">
					<Glyph name="gear" class="h-5 w-5" />
				</button>
			{/snippet}
			{#snippet children({ close })}
				<!-- Writers (admin) only: create/cancel are require_writer. -->
				{#if $isAdmin}
					<FlyoutItem
						onclick={() => {
							ripFromIso();
							close();
						}}
					>
						{#snippet icon()}
							<Glyph name="disc-3" />
						{/snippet}
						Rip from ISO
					</FlyoutItem>
					<FlyoutItem
						onclick={() => {
							ripFromFolder();
							close();
						}}
					>
						{#snippet icon()}
							<Glyph name="folder" />
						{/snippet}
						Rip from folder
					</FlyoutItem>
					<FlyoutDivider />
				{/if}
				<FlyoutItem
					onclick={() => {
						openSettings();
						close();
					}}
				>
					{#snippet icon()}
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
							/>
						</svg>
					{/snippet}
					Settings
				</FlyoutItem>
			{/snippet}
		</Flyout>
	{/if}
	{#if $isGuest}
		<button type="button" onclick={() => goto('/login')} class="btn btn-link" title="Log in"> Login </button>
	{:else}
		<button
			type="button"
			onclick={handleSignOut}
			class="btn btn-icon layout-header-icon"
			title="Sign out"
			aria-label="Sign out"
		>
			<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
				/>
			</svg>
		</button>
	{/if}
	<!-- Dark mode toggle (hidden when theme locks the mode) -->
	{#if !$schemeLocksMode}
		<button
			type="button"
			onclick={toggleTheme}
			class="btn btn-icon layout-header-icon"
			title="Switch theme"
			aria-label="Switch theme"
		>
			{#if $theme === 'dark'}
				<Glyph name="sun" class="h-5 w-5" />
			{:else}
				<Glyph name="moon" class="h-5 w-5" />
			{/if}
		</button>
	{/if}
</div>

<style>
	/* header icon buttons are 0.5rem/8px, not .btn-icon's default 0.375rem (6px) - that smaller value
	   is right for the denser row icon buttons elsewhere (channel rows use 6px), but would make
	   these four header buttons (sidebar toggle, quick actions, sign out, theme) ~2px narrower. */
	.layout-header-icon {
		padding: 0.5rem;
	}

	/* Auto-Start control: a labeled toggle, tinted by whether ripping is on.
	   Overrides the shared .btn box model (border, min-height, padding) back
	   to this control's own geometry (no border, natural height, 0.75rem/0.375rem padding), since .btn's border-strong ring and --control-h min-height
	   were designed for bordered action buttons, not this pill. */
	.layout-autostart {
		gap: 0.5rem;
		min-height: auto;
		padding: 0.375rem 0.75rem;
		border: 0;
		color: var(--color-on-warning-soft);
		background: var(--color-warning-soft);
	}
	.layout-autostart[data-active='true'] {
		color: var(--color-primary-text);
		background: var(--color-primary-tint-2);
	}
	/* Off/paused tint, scoped to aria-checked="false" so it does not outrank
	   toggle.css's [role="switch"][aria-checked="true"] > .toggle rule (a
	   scoped selector's Svelte hash otherwise wins that specificity fight
	   even when unconditional, since this button carries the real
	   role="switch" aria-checked). */
	.layout-autostart[aria-checked='false'] .toggle {
		background: var(--color-warning);
	}
</style>
