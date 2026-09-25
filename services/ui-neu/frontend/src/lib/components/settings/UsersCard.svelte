<script lang="ts">
	import { onMount } from 'svelte';
	import { reveal } from '$lib/transitions';
	import TimeAgo from '$lib/components/TimeAgo.svelte';
	import Toggle from '$lib/components/notifications/Toggle.svelte';
	import ChangePasswordForm from '$lib/components/settings/ChangePasswordForm.svelte';
	import CloseButton from '$lib/components/CloseButton.svelte';
	import { fetchUsers, setUserDisabled } from '$lib/api/users';
	import type { UserView } from '$lib/types/api.gen';

	let users = $state<UserView[]>([]);
	let loading = $state(true);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	const admin = $derived(users.find((u) => u.role === 'admin') ?? null);
	const guest = $derived(users.find((u) => u.role === 'guest') ?? null);

	// Which slide-over is open: 'admin-password' (change own password). Guest
	// sessions are passwordless (spec 2026-07-12-guest-autologin); the backend
	// password endpoint remains but is not surfaced here.
	let panel = $state<'admin-password' | null>(null);

	async function load() {
		loading = true;
		try {
			users = await fetchUsers();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Failed to load users' };
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function showFeedback(type: 'success' | 'error', message: string) {
		feedback = { type, message };
		setTimeout(() => { feedback = null; }, 4000);
	}

	function closePanel() {
		panel = null;
	}

	function openAdminPassword() {
		panel = 'admin-password';
	}

	function handleAdminPasswordSuccess() {
		closePanel();
		showFeedback('success', 'Admin password changed');
	}

	// Guest toggle: PATCHes disabled directly both ways — no password step,
	// since guest sessions are auto-acquired and passwordless.
	async function handleGuestToggle(next: boolean) {
		if (!guest) return;
		try {
			await setUserDisabled(guest.id, !next);
			await load();
			showFeedback('success', next ? 'Guest access enabled' : 'Guest access disabled');
		} catch (e) {
			showFeedback('error', e instanceof Error ? e.message : 'Failed to update guest access');
		}
	}

	// bg-blue-100/text-blue-700 and bg-amber-100/text-amber-700 were soft
	// tints, not badge-info/badge-warning's solid fills.
	function roleBadgeClass(role: string): string {
		return role === 'admin' ? 'users-card-role-badge-info' : 'users-card-role-badge-warning';
	}
</script>

<div class="panel">
	<h3 class="users-card-title">Users</h3>
	<p class="users-card-intro">Manage the admin password and guest access.</p>

	{#if feedback}
		<p in:reveal class="alert {feedback.type === 'success' ? 'alert-success' : 'alert-danger'} mb-3">
			{feedback.message}
		</p>
	{/if}

	{#if loading}
		<p class="users-card-loading">Loading...</p>
	{:else}
		<div class="stack users-card-rows">
			<!-- Admin row -->
			{#if admin}
				<div class="panel-section users-card-row">
					<div class="users-card-row-main">
						<span class="truncate users-card-username">{admin.username}</span>
						<span class="badge badge-sm users-card-role-badge {roleBadgeClass(admin.role)}">
							{admin.role}
						</span>
						<span class="users-card-meta">
							{admin.disabled ? 'Disabled' : 'Active'}
						</span>
						<span class="users-card-meta-faint">
							Last login: <TimeAgo date={admin.last_login_at ?? null} />
						</span>
					</div>
					<button
						type="button"
						onclick={openAdminPassword}
						class="btn btn-sm users-card-change-password-btn"
					>
						Change password
					</button>
				</div>
			{/if}

			<!-- Guest access: guests never sign in (sessions are anonymous), so there
			     is no username, status or last-login to show, just the switch. -->
			{#if guest}
				<div class="panel-section users-card-row" data-testid="guest-access-row">
					<div class="field users-card-guest-info">
						<span class="field-label users-card-guest-label">Guest access</span>
						<p class="field-help">
							Let anyone on the network browse without signing in. Guests can view but not change anything.
						</p>
					</div>
					<div class="flex shrink-0 items-center gap-2">
						<span class="users-card-guest-state">{guest.disabled ? 'Off' : 'On'}</span>
						<Toggle checked={!guest.disabled} label="guest" onchange={handleGuestToggle} />
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>

<!-- ── Admin change-password slide-over (copied from SessionsArea's inline-preset slide-over) ── -->
{#if panel === 'admin-password'}
	<div role="presentation" class="users-card-scrim" onclick={closePanel}></div>
	<div
		role="dialog"
		aria-modal="true"
		aria-label="Change password"
		class="slide-over-panel users-card-panel flex flex-col"
	>
		<div class="slide-over-header">
			<h2 class="modal-title">Change password</h2>
			<CloseButton onclick={closePanel} />
		</div>
		<div class="flex-1 overflow-y-auto p-6">
			<ChangePasswordForm onsuccess={handleAdminPasswordSuccess} />
		</div>
	</div>
{/if}

<style>
	/* the card's own eyebrow-title/hint gap was tighter than the panel
	   default's 0.75rem margin, and its intro line sits directly under the
	   title with no list below it yet. */
	/* both were text-sm text-gray-500 (0.875rem/1.25rem), not panel-hint's
	   0.75rem - panel-hint is sized for a note under a form control, a
	   visibly smaller role. */
	/* text-base font-semibold text-gray-900, mb-1 - a plain heading, not
	   panel-title's uppercase eyebrow look. */
	.users-card-title { margin-bottom: 0.25rem; font-size: 1rem; line-height: 1.5rem; font-weight: 600; color: var(--color-text); }
	.users-card-intro { margin-bottom: 1rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.users-card-loading { padding: 1rem 0; text-align: center; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-faint); }
	/* the original row list was space-y-3 (0.75rem) - between stack-sm's
	   0.5rem and stack's own 1rem, so neither modifier matches exactly. */
	.users-card-rows { gap: 0.75rem; }
	/* the original rows were bordered, rounded boxes (rounded-lg
	   border-primary/10 px-3 py-2.5) with no fill - panel-section's shape,
	   but at 10% primary border (tint-2) instead of --color-border's 18%,
	   its own 0.625rem/0.75rem padding, and no tint background. */
	.users-card-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.625rem 0.75rem; border-color: var(--color-primary-tint-2); background: none; }
	/* Tailwind's flex-1 is `flex: 1 1 0%` - a zero basis, so the lead can
	   shrink below its content width and its truncate/shrink-0 children
	   absorb the squeeze. `flex: 1 1 auto` (a content-width basis) instead
	   overflows the row and pushes the trailing control onto its own line
	   at the mobile width. */
	.users-card-row-main { display: flex; min-width: 0; flex: 1 1 0%; align-items: center; gap: 0.5rem; }
	/* the guest row's label + description stack vertically (the original
	   was min-w-0 flex-1, a plain block wrapper) - .field already handles
	   that layout; users-card-row-main's flex-row + align-items:center
	   would put them side by side instead. */
	.users-card-guest-info { min-width: 0; flex: 1 1 0%; }
	/* the original label was text-gray-900 dark:text-white - the full-
	   contrast text role, not field-label's --color-text-secondary. */
	.users-card-guest-label { color: var(--color-text); }
	/* the original role badge was text-xs font-bold tracking-widest
	   (12px/700/0.1em), not badge-sm's 10px/500/0.06em. */
	.users-card-role-badge { font-size: 0.75rem; font-weight: 700; letter-spacing: 0.1em; }
	.users-card-role-badge-info { background: var(--color-info-soft); color: var(--color-on-info-soft); }
	.users-card-role-badge-warning { background: var(--color-warning-soft); color: var(--color-on-warning-soft); }
	/* the original was border-primary/30 bg-primary/10 text-primary (a
	   tinted fill with a border), not .btn's plain outlined default. Its
	   text-xs also carried Tailwind's bundled 1rem line-height, which
	   .btn-sm (font-size only) leaves at .btn's own 1.25rem - 4px taller
	   than the original 26px button, which set the whole row's height. */
	.users-card-change-password-btn { min-height: 0; line-height: 1rem; border-color: var(--color-border-strong); background: var(--color-primary-tint-2); color: var(--color-primary); }
	.users-card-change-password-btn:hover { background: var(--color-primary-tint-3); }
	.users-card-username { font-size: 0.875rem; font-weight: 500; color: var(--color-text); }
	/* text-xs text-gray-500 - a plain inline span in a flex row, not
	   panel-hint's block-level note (whose own margin-top would misalign
	   it against its row siblings). */
	.users-card-meta { flex-shrink: 0; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.users-card-guest-state { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.users-card-meta-faint { flex-shrink: 0; font-size: 0.75rem; color: var(--color-text-faint); }
	/* UsersCard renders its own backdrop + panel (not the SlideOver
	   component, which needs a headerActions/onclose contract this form
	   doesn't use), matching SlideOver.svelte's own fixed positioning:
	   a full-screen scrim under a right-anchored panel, both fixed since
	   neither is portaled here. */
	.users-card-scrim { position: fixed; inset: 0; z-index: 40; background: var(--color-backdrop); }
	.users-card-panel { position: fixed; top: 0; right: 0; bottom: 0; z-index: 50; width: 100%; max-width: 32rem; }
</style>
