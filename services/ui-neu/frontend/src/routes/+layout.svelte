<script lang="ts">
	import '../app.css';
	import { page } from '$app/stores';
	import { theme, toggleTheme } from '$lib/stores/theme';
	import { colorScheme, schemeLocksMode, loadThemesFromApi } from '$lib/stores/colorScheme';
	import { dashboard } from '$lib/stores/dashboard';
	import { transcoderEnabled } from '$lib/stores/config';
	import { setRippingEnabled } from '$lib/api/dashboard';
	import { goto } from '$app/navigation';
	import { showImportWizard } from '$lib/stores/importWizard';
	import ImportWizard from '$lib/components/ImportWizard.svelte';
	import Flyout from '$lib/components/Flyout.svelte';
	import FlyoutItem from '$lib/components/FlyoutItem.svelte';
	import FlyoutDivider from '$lib/components/FlyoutDivider.svelte';
	import { onMount } from 'svelte';
	import { setUnauthorizedHandler } from '$lib/api/client';
	import { logoutLocal, initAuth, isGuest } from '$lib/stores/auth';
	import { uiPrefs } from '$lib/stores/uiPrefs';
	import { isScreenEnabled } from '$lib/features';
	import { logout as apiLogout } from '$lib/api/auth';
	import { countRipping } from '$lib/utils/job-status';
	import BottomStatsBar from '$lib/components/BottomStatsBar.svelte';
	import SidebarStats from '$lib/components/SidebarStats.svelte';
	import MobileStatsPanel from '$lib/components/MobileStatsPanel.svelte';
	let { children } = $props();

	let sidebarOpen = $state(false);
	// Mobile drawer view — resets to 'menu' every time the drawer opens, so
	// navigation (the drawer's primary job) is always one tap away.
	let drawerView = $state<'menu' | 'stats'>('menu');

	function openSidebar() {
		drawerView = 'menu';
		sidebarOpen = true;
	}
	let togglingPause = $state(false);
	// Guards the 401 handler against firing redundant goto('/login') calls when
	// multiple in-flight requests 401 at once. Reset once the user is back on a
	// real (non-auth) page, so a future session expiry can redirect again.
	let redirectingToLogin = false;

	const rippingCount = $derived(countRipping($dashboard.active_jobs ?? []));

	function handleQuickAction(action: string) {
		if (action === 'import-folder') {
			showImportWizard.set(true);
		} else if (action === 'settings') {
			goto('/settings');
		}
	}

	let isSetupPage = $derived($page.url.pathname.startsWith('/setup'));
	let isAuthPage = $derived(
		$page.url.pathname.startsWith('/login') || $page.url.pathname.startsWith('/change-password')
	);
	// Once the user is back on a real page (logged in again), re-arm the 401
	// redirect guard so a later session expiry can route to /login afresh.
	$effect(() => {
		if (!isAuthPage) redirectingToLogin = false;
	});

	// Guests have no access to /settings (server also enforces this) — bounce
	// them to the dashboard if they land there via a stale link or back-nav.
	$effect(() => {
		if ($isGuest && $page.url.pathname.startsWith('/settings')) {
			goto('/');
		}
	});

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
		dashboard.update(d => ({ ...d, ripping_enabled: newValue }));
		try {
			await setRippingEnabled(newValue);
		} catch {
			// Revert on failure — next poll will also reconcile
			dashboard.update(d => ({ ...d, ripping_enabled: !newValue }));
		} finally {
			togglingPause = false;
		}
	}

	onMount(() => {
		initAuth();
		// Register the 401 handler ONCE here. It MUST route through logoutLocal
		// (not client.clearToken directly) so the in-memory auth store and the
		// persisted token clear together, then redirect to /login.
		//
		// The dashboard poll (a 6-endpoint allSettled fan-out every 5s) survives
		// `goto('/login')` because the root layout persists across navigations —
		// so it would keep firing requests that 401, re-entering this handler
		// many times per tick and re-navigating to /login on each (which steals
		// focus from the login inputs). Fix: stop the poll loop the moment the
		// session is known stale, and guard the redirect so repeated 401s from
		// in-flight requests don't pile up redundant navigations.
		setUnauthorizedHandler(() => {
			dashboard.stop();
			logoutLocal();
			if (!redirectingToLogin) {
				redirectingToLogin = true;
				goto('/login');
			}
		});
		// Auth pages (/login, /change-password) render bare and must NOT poll the
		// dashboard — the user has no usable session there, so the poll would 401
		// (login) or 403 (change-password) on a loop.
		if ($page.url.pathname.startsWith('/login') || $page.url.pathname.startsWith('/change-password')) {
			return;
		}
		// Load themes from API (falls back to built-in if backend unreachable)
		loadThemesFromApi();
		// Tokenless browsing is a valid state (anonymous requests act as guest
		// backend-side) — start polling the same as an authenticated session.
		dashboard.start();
		return () => dashboard.stop();
	});

	const allNavItems = [
		{ href: '/', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
		{ href: '/notifications', label: 'Notifications', icon: 'M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9' },
		{ href: '/logs', label: 'Logs', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
		{ href: '/files', label: 'Files', icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z' },
		{ href: '/transcoder', label: 'Transcoder', icon: 'M7 4V2a1 1 0 012 0v2h6V2a1 1 0 012 0v2h1a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h1zm0 8h10m-10 4h6' },
		{ href: '/settings', label: 'Settings', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
	];
	const navItems = $derived(
		allNavItems
			.filter(i => isScreenEnabled(i.href))
			.filter(i => i.href !== '/transcoder' || $transcoderEnabled)
			.filter(i => i.href !== '/settings' || !$isGuest)
	);

	function isActive(href: string, pathname: string): boolean {
		if (href === '/') return pathname === '/';
		return pathname.startsWith(href);
	}
</script>

{#if isSetupPage || isAuthPage}
	<div class={$theme}>
		{@render children()}
	</div>
{:else}
<div class="flex h-screen overflow-hidden">
	<!-- Sidebar -->
	<aside class="sidebar hidden lg:block">
		<div class="flex h-full flex-col">
			<div data-logo class="nav-logo">
				<img src="/img/arm-logo-black.png" alt="ARM" class="layout-logo-light" />
				<img src="/img/arm-logo-white.png" alt="ARM" class="layout-logo-dark" />
			</div>
			<hr class="layout-hr" />
			<nav class="nav flex-1 overflow-y-auto">
				{#each navItems as item}
					<a
						href={item.href}
						data-active={isActive(item.href, $page.url.pathname) || undefined}
						class="nav-item"
					>
						<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={item.icon} />
						</svg>
						{item.label}
						{#if item.href === '/notifications' && ($dashboard.notification_count ?? 0) > 0}
							<span class="nav-badge">{$dashboard.notification_count}</span>
						{/if}
					</a>
				{/each}
			</nav>
			<!-- Sidebar stats only at 2xl+, where the bottom bar (lg:flex 2xl:hidden)
			     is hidden — the two surfaces never show at the same viewport width. -->
			{#if $uiPrefs.showStats}
				<div class="hidden 2xl:block">
					<SidebarStats />
				</div>
			{/if}
		</div>
	</aside>

	<!-- Main content -->
	<div class="flex flex-1 flex-col overflow-hidden">
		<!-- Top bar -->
		<header class="layout-header flex h-14 items-center justify-between px-4 lg:px-6">
			<button
				onclick={() => sidebarOpen ? (sidebarOpen = false) : openSidebar()}
				aria-label="Toggle sidebar"
				class="btn btn-icon layout-header-icon lg:hidden"
			>
				<svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
				</svg>
			</button>

			<!-- Stats bar (desktop only) -->
			<div class="layout-stats-bar hidden lg:flex items-center gap-3">
				<!-- Service health dots -->
				<div class="flex items-center gap-3">
					<svelte:element this={$isGuest ? 'span' : 'a'} href={$isGuest ? undefined : '/settings#system'} class="layout-health-link">
						<span class="status-dot" data-status={$dashboard.arm_online ? 'ok' : 'error'}></span>
						<span class="layout-health-label">ARM</span>
					</svelte:element>
					<svelte:element this={$isGuest ? 'span' : 'a'} href={$isGuest ? undefined : '/settings#system'} class="layout-health-link">
						<span class="status-dot" data-status={$dashboard.db_available ? 'ok' : 'warn'}></span>
						<span class="layout-health-label">DB</span>
					</svelte:element>
					<a href="/transcoder" class="layout-health-link">
						<span
							class="status-dot"
							data-status={$dashboard.transcoder_online && ($dashboard.transcoder_stats?.worker_running ?? true)
								? 'ok'
								: $dashboard.transcoder_online
									? 'warn'
									: 'off'}
						></span>
						<span class="layout-health-label">Transcode</span>
					</a>
					<svelte:element this={$isGuest ? 'span' : 'a'} href={$isGuest ? undefined : '/settings#Metadata/makemkv_key'} class="layout-health-link"
						title={$dashboard.makemkv_key_valid === true
							? `MakeMKV key valid${$dashboard.makemkv_key_checked_at ? ' - checked ' + new Date($dashboard.makemkv_key_checked_at).toLocaleString() : ''}`
							: $dashboard.makemkv_key_valid === false
								? 'MakeMKV key invalid - click to update'
								: 'MakeMKV key not checked yet'}
					>
						<span class="status-dot" data-status={$dashboard.makemkv_key_valid === true ? 'ok' : 'error'}></span>
						<span class="layout-health-label">Key</span>
					</svelte:element>
				</div>
				<!-- Divider -->
				<div class="layout-header-divider"></div>
				<!-- Live activity -->
				<div class="layout-activity-group flex items-center gap-3">
					<svelte:element this={$isGuest ? 'span' : 'a'} href={$isGuest ? undefined : '/settings#drives'} class="layout-activity-link">{$dashboard.db_available ? $dashboard.drives_online : '--'} drive{$dashboard.drives_online !== 1 ? 's' : ''}</svelte:element>
					{#if rippingCount > 0}
						<span class="layout-activity-ripping">{rippingCount} ripping</span>
					{/if}
					{#if $dashboard.active_transcodes.length > 0}
						<a href="/transcoder" class="layout-activity-transcoding">{$dashboard.active_transcodes.length} transcoding</a>
					{/if}
					{#if $dashboard.transcoder_online && (Number($dashboard.transcoder_stats?.pending) || 0) > 0}
						<span class="layout-activity-queued">{$dashboard.transcoder_stats?.pending} queued</span>
					{/if}
					{#if ($dashboard.notification_count ?? 0) > 0}
						<a href="/notifications" class="layout-activity-notification">{$dashboard.notification_count} notification{$dashboard.notification_count !== 1 ? 's' : ''}</a>
					{/if}
				</div>
			</div>

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
						<button
							onclick={toggle}
							class="btn btn-icon layout-header-icon"
							title="Quick actions"
						>
							<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
							</svg>
						</button>
					{/snippet}
					{#snippet children({ close })}
						<FlyoutItem onclick={() => { handleQuickAction('import-folder'); close(); }}>
							{#snippet icon()}
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
								</svg>
							{/snippet}
							Import
						</FlyoutItem>
						<FlyoutDivider />
						<FlyoutItem onclick={() => { handleQuickAction('settings'); close(); }}>
							{#snippet icon()}
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
								</svg>
							{/snippet}
							Settings
						</FlyoutItem>
					{/snippet}
				</Flyout>
				{/if}
				{#if $isGuest}
					<button
						onclick={() => goto('/login')}
						class="btn btn-link"
						title="Log in"
					>
						Login
					</button>
				{:else}
					<button
						onclick={handleSignOut}
						class="btn btn-icon layout-header-icon"
						title="Sign out"
						aria-label="Sign out"
					>
						<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
						</svg>
					</button>
				{/if}
				<!-- Dark mode toggle (hidden when theme locks the mode) -->
				{#if !$schemeLocksMode}
					<button
						onclick={toggleTheme}
						class="btn btn-icon layout-header-icon"
					>
						{#if $theme === 'dark'}
							<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
							</svg>
						{:else}
							<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
							</svg>
						{/if}
					</button>
				{/if}
			</div>
		</header>

		<!-- Mobile sidebar overlay -->
		{#if sidebarOpen}
			<div class="layout-drawer-overlay fixed inset-0 lg:hidden">
				<button class="layout-scrim absolute inset-0" aria-label="Close sidebar" onclick={() => sidebarOpen = false}></button>
				<aside class="layout-drawer relative flex h-full flex-col">
					<div data-logo class="nav-logo layout-drawer-logo">
						<img src="/img/arm-logo-black.png" alt="ARM" class="layout-logo-light layout-logo-sm" />
						<img src="/img/arm-logo-white.png" alt="ARM" class="layout-logo-dark layout-logo-sm" />
					</div>
					<!-- Menu / Stats view toggle -->
					<div class="tabs tabs-pills layout-drawer-tabs mx-3 mb-2 grid grid-cols-2">
						{#each [{ id: 'menu', label: 'Menu' }, { id: 'stats', label: 'Stats' }] as view (view.id)}
							<button
								type="button"
								data-active={drawerView === view.id}
								onclick={() => drawerView = view.id as 'menu' | 'stats'}
								class="tabs-tab layout-drawer-tab"
							>
								{view.label}
							</button>
						{/each}
					</div>
					<hr class="layout-hr" />
					{#if drawerView === 'menu'}
						<nav class="nav flex-1 overflow-y-auto">
							{#each navItems as item}
								<a
									href={item.href}
									onclick={() => sidebarOpen = false}
									data-active={isActive(item.href, $page.url.pathname) || undefined}
									class="nav-item"
								>
									<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={item.icon} />
									</svg>
									{item.label}
									{#if item.href === '/notifications' && ($dashboard.notification_count ?? 0) > 0}
										<span class="nav-badge">{$dashboard.notification_count}</span>
									{/if}
								</a>
							{/each}
						</nav>
					{:else}
						<MobileStatsPanel onnavigate={() => sidebarOpen = false} />
					{/if}
				</aside>
			</div>
		{/if}

		<!-- Page content -->
		<main class="flex-1 overflow-y-auto p-4 lg:p-6">
			{@render children()}
		</main>
	</div>
</div>
{/if}
{#if $uiPrefs.showStats}
	<BottomStatsBar />
{/if}

<!-- Folder import wizard (global, triggered from gear menu) -->
<ImportWizard
	open={$showImportWizard}
	onclose={() => showImportWizard.set(false)}
	oncreated={() => { showImportWizard.set(false); }}
/>

<style>
	/* Sidebar shell: the one arrangement rule the block vocabulary doesn't
	   cover (a nav host needs a fixed width and a border, .nav itself is
	   just the link list). */
	.sidebar {
		width: 16rem;
		flex-shrink: 0;
		border-right: 1px solid var(--color-border);
		background: var(--color-surface);
	}
	.layout-stats-bar {
		font-size: 0.875rem;
	}
	.layout-activity-group {
		font-size: 0.75rem;
	}
	.layout-header {
		border-bottom: 1px solid var(--color-border);
		background: var(--color-surface);
	}
	.layout-hr {
		border-top: 1px solid var(--color-border);
	}
	.layout-header-divider {
		height: 1.5rem;
		width: 1px;
		background: var(--color-border-strong);
	}
	/* original header icon buttons were p-2 (0.5rem/8px), not .btn-icon's
	   default 0.375rem (6px) - that smaller value is right for the denser
	   row icon buttons elsewhere (channel rows use p-1.5/6px), but shifts
	   these four header buttons (sidebar toggle, quick actions, sign out,
	   theme) ~2px narrower than the original. */
	.layout-header-icon {
		padding: 0.5rem;
	}
	.layout-logo-light, .layout-logo-dark {
		height: 6rem;
		width: 6rem;
	}
	.layout-logo-sm {
		height: 5rem;
		width: 5rem;
	}
	.layout-logo-dark { display: none; }
	/* The ARM wordmark is two pre-rendered bitmaps (black-on-transparent,
	   white-on-transparent); dark mode swaps which one is visible. */
	:global(.dark) .layout-logo-light { display: none; } /* hide the black wordmark */
	:global(.dark) .layout-logo-dark { display: block; } /* swap to the white wordmark */

	/* Service health dots: label + hover affordance shared by all four rows. */
	.layout-health-link {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		transition: opacity var(--motion-fast) var(--ease);
	}
	a.layout-health-link:hover {
		opacity: 0.75;
	}
	.layout-health-label {
		color: var(--color-text-secondary);
	}
	.layout-activity-link {
		color: var(--color-text-muted);
		transition: color var(--motion-fast) var(--ease);
	}
	a.layout-activity-link:hover {
		color: var(--color-primary-text);
	}
	/* Four distinct count tones. These are TEXT labels, so they take the
	   accent roles that match their originals (blue-400, indigo-400,
	   amber-400), not the --color-status-* machine that fills dots and
	   progress bars: a scheme is free to redefine the status colours for its
	   own state machine (winamp-97 sets every one of them to terminal green),
	   which would collapse all four counts into one colour. */
	.layout-activity-ripping {
		font-weight: 600;
		color: var(--color-accent-2);
	}
	.layout-activity-transcoding {
		font-weight: 600;
		color: var(--color-accent-3);
	}
	.layout-activity-queued {
		font-weight: 600;
		color: var(--color-accent-1);
	}
	.layout-activity-notification {
		font-weight: 600;
		color: var(--color-warning);
	}
	a.layout-activity-transcoding:hover,
	a.layout-activity-notification:hover {
		color: var(--color-primary-hover);
	}

	/* Auto-Start control: a labeled toggle, tinted by whether ripping is on.
	   Overrides the shared .btn box model (border, min-height, padding) back
	   to this control's original geometry (no border, natural height,
	   px-3 py-1.5), since .btn's border-strong ring and --control-h min-height
	   were designed for bordered action buttons, not this pill. */
	.layout-autostart {
		gap: 0.5rem;
		min-height: auto;
		padding: 0.375rem 0.75rem;
		border: 0;
		color: var(--color-on-warning-soft);
		background: var(--color-warning-soft);
	}
	.layout-autostart[data-active="true"] {
		color: var(--color-primary-text);
		background: var(--color-primary-tint-2);
	}
	/* Off/paused tint, scoped to aria-checked="false" so it does not outrank
	   toggle.css's [role="switch"][aria-checked="true"] > .toggle rule (a
	   scoped selector's Svelte hash otherwise wins that specificity fight
	   even when unconditional, since this button carries the real
	   role="switch" aria-checked). */
	.layout-autostart[aria-checked="false"] .toggle {
		background: var(--color-warning);
	}

	/* Mobile drawer */
	.layout-drawer-overlay {
		z-index: 40;
	}
	.layout-scrim {
		z-index: 50;
		background: var(--color-backdrop);
	}
	.layout-drawer {
		z-index: 50;
		width: 16rem;
		background: var(--color-surface);
		box-shadow: var(--shadow-2);
	}
	.layout-drawer-logo {
		padding-top: 1rem;
		padding-bottom: 1rem;
	}
	.layout-drawer-tabs {
		background: var(--color-primary-tint-2);
		padding: 0.25rem;
		border-radius: var(--radius-lg);
	}
	.layout-drawer-tab {
		text-align: center;
		padding: 0.375rem 0.75rem;
		line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-text-muted);
	}
	.layout-drawer-tab:hover {
		color: var(--color-text);
	}
	/* Plain buttons, not role="tab" (the drawer's Menu/Stats toggle is not a
	   tabpanel switcher in the ARIA sense), so the selected look keys off
	   data-active rather than the tabs block's own aria-selected hook. The
	   active tone is the tinted one this control has always used (the same
	   tint/text pair as an active nav-item), not tabs-pills' solid fill. */
	.layout-drawer-tab[data-active="true"] {
		/* Opaque, not the transparent tint token: the strip underneath is
		   already tinted, and a second translucent tint on top would stack
		   into a visibly darker pill than the flat one this control has. */
		background: color-mix(in srgb, var(--color-primary) 10%, var(--color-surface));
		color: var(--color-primary-text);
	}
</style>
