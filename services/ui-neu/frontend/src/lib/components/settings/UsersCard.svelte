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

	function roleBadgeClass(role: string): string {
		return role === 'admin'
			? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
			: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300';
	}
</script>

<div class="rounded-lg border border-primary/20 bg-surface p-4 shadow-xs dark:bg-surface-dark">
	<h3 class="mb-1 text-base font-semibold text-gray-900 dark:text-white">Users</h3>
	<p class="mb-4 text-sm text-gray-500 dark:text-gray-400">Manage the admin password and guest access.</p>

	{#if feedback}
		<p in:reveal class="mb-3 rounded px-3 py-2 text-sm {feedback.type === 'success' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'}">
			{feedback.message}
		</p>
	{/if}

	{#if loading}
		<p class="py-4 text-center text-sm text-gray-400">Loading...</p>
	{:else}
		<div class="space-y-3">
			<!-- Admin row -->
			{#if admin}
				<div class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-primary/10 px-3 py-2.5 dark:border-primary/10">
					<div class="flex min-w-0 flex-1 items-center gap-2">
						<span class="truncate font-medium text-sm text-gray-900 dark:text-white">{admin.username}</span>
						<span class="shrink-0 rounded px-1.5 py-0.5 text-xs font-bold uppercase tracking-widest {roleBadgeClass(admin.role)}">
							{admin.role}
						</span>
						<span class="shrink-0 text-xs text-gray-500 dark:text-gray-400">
							{admin.disabled ? 'Disabled' : 'Active'}
						</span>
						<span class="shrink-0 text-xs text-gray-400 dark:text-gray-500">
							Last login: <TimeAgo date={admin.last_login_at ?? null} />
						</span>
					</div>
					<button
						type="button"
						onclick={openAdminPassword}
						class="shrink-0 rounded-md border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary hover:bg-primary/20"
					>
						Change password
					</button>
				</div>
			{/if}

			<!-- Guest access: guests never sign in (sessions are anonymous), so there
			     is no username, status or last-login to show, just the switch. -->
			{#if guest}
				<div class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-primary/10 px-3 py-2.5 dark:border-primary/10" data-testid="guest-access-row">
					<div class="min-w-0 flex-1">
						<span class="text-sm font-medium text-gray-900 dark:text-white">Guest access</span>
						<p class="text-xs text-gray-500 dark:text-gray-400">
							Let anyone on the network browse without signing in. Guests can view but not change anything.
						</p>
					</div>
					<div class="flex shrink-0 items-center gap-2">
						<span class="text-xs text-gray-500 dark:text-gray-400">{guest.disabled ? 'Off' : 'On'}</span>
						<Toggle checked={!guest.disabled} label="guest" onchange={handleGuestToggle} />
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>

<!-- ── Admin change-password slide-over (copied from SessionsArea's inline-preset slide-over) ── -->
{#if panel === 'admin-password'}
	<div role="presentation" class="fixed inset-0 z-60 bg-black/50" onclick={closePanel}></div>
	<div
		role="dialog"
		aria-modal="true"
		aria-label="Change password"
		class="fixed inset-y-0 right-0 z-70 flex w-full max-w-lg flex-col overflow-y-auto bg-white shadow-xl dark:bg-gray-900"
	>
		<div class="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-700">
			<h2 class="text-lg font-semibold text-gray-900 dark:text-white">Change password</h2>
			<CloseButton onclick={closePanel} />
		</div>
		<div class="flex-1 overflow-y-auto p-6">
			<ChangePasswordForm onsuccess={handleAdminPasswordSuccess} />
		</div>
	</div>
{/if}
