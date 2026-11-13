<script lang="ts">
	import '../app.css';
	import { page } from '$app/stores';
	import { loadThemesFromApi } from '$lib/stores/color-scheme';
	import { theme } from '$lib/stores/theme';
	import { dashboard } from '$lib/stores/dashboard';
	import { transcoderEnabled } from '$lib/stores/config';
	import { goto } from '$app/navigation';
	import { isoPickerMode, showIsoPicker } from '$lib/stores/iso-picker';
	import IsoPicker from '$lib/components/IsoPicker.svelte';
	import { onMount } from 'svelte';
	import { setUnauthorizedHandler } from '$lib/api/client';
	import { logoutLocal, initAuth, isGuest, isAdmin } from '$lib/stores/auth';
	import { uiPrefs } from '$lib/stores/ui-prefs';
	import { NAV_ITEMS, visibleNavItems } from '$lib/nav';
	import NavList from '$lib/components/NavList.svelte';
	import HeaderActions from '$lib/components/HeaderActions.svelte';
	import HeaderStatus from '$lib/components/HeaderStatus.svelte';
	import BottomStatsBar from '$lib/components/BottomStatsBar.svelte';
	import LiveUpdatesBanner from '$lib/components/LiveUpdatesBanner.svelte';
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
	// Guards the 401 handler against firing redundant goto('/login') calls when
	// multiple in-flight requests 401 at once. Reset once the user is back on a
	// real (non-auth) page, so a future session expiry can redirect again.
	let redirectingToLogin = false;

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
	});

	// Auth pages (/login, /change-password) render bare and must NOT poll the
	// dashboard: the user has no usable session there, so the poll would 401
	// (login) or 403 (change-password) on a loop. The root layout persists
	// across navigations, so the poll starts whenever the visitor reaches a real
	// page (first load, after signing in, after a session expiry) and stops on
	// the way back to an auth page. Tokenless browsing is a valid state
	// (anonymous requests act as guest backend-side), so it polls the same as an
	// authenticated session.
	let themesLoaded = false;
	$effect(() => {
		if (isAuthPage) return;
		if (!themesLoaded) {
			themesLoaded = true;
			// Falls back to the built-in themes if the backend is unreachable.
			loadThemesFromApi();
		}
		dashboard.start();
		return () => dashboard.stop();
	});

	const navItems = $derived(visibleNavItems(NAV_ITEMS, { transcoderEnabled: $transcoderEnabled, isGuest: $isGuest }));
</script>

{#if isSetupPage || isAuthPage}
	<div class={$theme}>
		{@render children()}
	</div>
{:else}
	<div class="flex h-screen overflow-hidden">
		<!-- Sidebar -->
		<aside data-sidebar class="sidebar hidden lg:block">
			<div class="flex h-full flex-col">
				<div data-logo class="nav-logo">
					<img src="/img/arm-logo-black.png" alt="ARM" class="layout-logo-light" />
					<img src="/img/arm-logo-white.png" alt="ARM" class="layout-logo-dark" />
				</div>
				<hr class="layout-hr" />
				<NavList items={navItems} pathname={$page.url.pathname} notificationCount={$dashboard.notification_count} />
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
					onclick={() => (sidebarOpen ? (sidebarOpen = false) : openSidebar())}
					aria-label="Toggle sidebar"
					class="btn btn-icon layout-header-icon lg:hidden"
				>
					<svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
					</svg>
				</button>

				<!-- Stats bar (desktop only) -->
				<HeaderStatus />

				<HeaderActions />
			</header>

			<!-- Mobile sidebar overlay -->
			{#if sidebarOpen}
				<div class="layout-drawer-overlay fixed inset-0 lg:hidden">
					<button class="layout-scrim absolute inset-0" aria-label="Close sidebar" onclick={() => (sidebarOpen = false)}
					></button>
					<aside data-sidebar class="layout-drawer relative flex h-full flex-col">
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
									onclick={() => (drawerView = view.id as 'menu' | 'stats')}
									class="tabs-tab layout-drawer-tab"
								>
									{view.label}
								</button>
							{/each}
						</div>
						<hr class="layout-hr" />
						{#if drawerView === 'menu'}
							<NavList
								items={navItems}
								pathname={$page.url.pathname}
								notificationCount={$dashboard.notification_count}
								onnavigate={() => (sidebarOpen = false)}
							/>
						{:else}
							<MobileStatsPanel onnavigate={() => (sidebarOpen = false)} />
						{/if}
					</aside>
				</div>
			{/if}

			<!-- Page content -->
			<main data-stats-bar={$uiPrefs.showStats || undefined} class="layout-main flex-1 overflow-y-auto p-4 lg:p-6">
				<LiveUpdatesBanner />
				{@render children()}
			</main>
		</div>
	</div>
{/if}
<!-- The setup walkthrough is a focused shell: no resource footer (setup spec §5.0). -->
{#if $uiPrefs.showStats && !isSetupPage}
	<BottomStatsBar />
{/if}

<!-- ISO picker (global, triggered from gear menu; writers only) -->
{#if $isAdmin}
	<IsoPicker
		open={$showIsoPicker}
		mode={$isoPickerMode}
		onclose={() => showIsoPicker.set(false)}
		onstarted={() => {
			showIsoPicker.set(false);
		}}
	/>
{/if}

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
	/* The fixed BottomStatsBar (h-10, shown lg to 2xl) overlays main's
	   bottom edge; viewport-sized content in main (help's sticky rails)
	   subtracts this to end above it. */
	@media (min-width: 64rem) and (max-width: 95.98rem) {
		.layout-main[data-stats-bar] {
			--shell-footer-height: 2.5rem;
		}
	}
	.layout-header {
		border-bottom: 1px solid var(--color-border);
		background: var(--color-surface);
	}
	.layout-hr {
		border-top: 1px solid var(--color-border);
	}
	/* original header icon buttons were p-2 (0.5rem/8px), not .btn-icon's
	   default 0.375rem (6px) - that smaller value is right for the denser
	   row icon buttons elsewhere (channel rows use p-1.5/6px), but shifts
	   these four header buttons (sidebar toggle, quick actions, sign out,
	   theme) ~2px narrower than the original. */
	.layout-header-icon {
		padding: 0.5rem;
	}
	.layout-logo-light,
	.layout-logo-dark {
		height: 6rem;
		width: 6rem;
	}
	.layout-logo-sm {
		height: 5rem;
		width: 5rem;
	}
	.layout-logo-dark {
		display: none;
	}
	/* The ARM wordmark is two pre-rendered bitmaps (black-on-transparent,
	   white-on-transparent); dark mode swaps which one is visible. */
	/* hide the black wordmark */
	:global(.dark) .layout-logo-light {
		display: none;
	}
	/* swap to the white wordmark */
	:global(.dark) .layout-logo-dark {
		display: block;
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
	.layout-drawer-tab[data-active='true'] {
		/* Opaque, not the transparent tint token: the strip underneath is
		   already tinted, and a second translucent tint on top would stack
		   into a visibly darker pill than the flat one this control has. */
		background: color-mix(in srgb, var(--color-primary) 10%, var(--color-surface));
		color: var(--color-primary-text);
	}
</style>
