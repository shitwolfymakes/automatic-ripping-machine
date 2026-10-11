<script lang="ts">
	import { onMount } from 'svelte';
	import Toggle from '$lib/components/notifications/Toggle.svelte';
	import { fetchUsers, setUserDisabled } from '$lib/api/users';
	import type { UserView } from '$lib/types/api.gen';

	// Guest access on/off, shared by Settings > Users and the setup walkthrough.
	// Settings: an immediate-effect Toggle. Setup (`deferred`): a checkbox that
	// saves when the parent calls `save()` on Continue. Pass `guest` when the
	// parent already has the users list; otherwise the field loads it.
	let {
		guest: guestProp,
		deferred = false,
		onsaved,
		onerror
	}: {
		guest?: UserView | null;
		deferred?: boolean;
		onsaved?: (enabled: boolean) => void;
		onerror?: (message: string) => void;
	} = $props();

	let loaded = $state<UserView | null>(null);
	const guest = $derived(guestProp !== undefined ? guestProp : loaded);
	// Follows the account until the operator ticks it; save() persists it.
	let checked = $derived(guest ? !guest.disabled : false);
	let saving = $state(false);

	onMount(async () => {
		if (guestProp !== undefined) return;
		try {
			loaded = (await fetchUsers()).find((u) => u.role === 'guest') ?? null;
		} catch {
			loaded = null;
		}
	});

	async function apply(enabled: boolean): Promise<void> {
		if (!guest) return;
		saving = true;
		try {
			await setUserDisabled(guest.id, !enabled);
			if (guestProp === undefined) loaded = { ...guest, disabled: !enabled };
			onsaved?.(enabled);
		} catch (e) {
			const message = e instanceof Error ? e.message : 'Failed to update guest access';
			onerror?.(message);
			throw e;
		} finally {
			saving = false;
		}
	}

	/** Deferred mode: persist the checkbox if it changed. */
	export async function save(): Promise<void> {
		if (!guest || checked === !guest.disabled) return;
		await apply(checked);
	}

	async function toggle(next: boolean) {
		try {
			await apply(next);
		} catch {
			/* reported through onerror */
		}
	}
</script>

{#if guest}
	{#if deferred}
		<label class="field field-row guest-access-field" data-testid="guest-access-row">
			<input type="checkbox" bind:checked disabled={saving} />
			<span>
				<span class="guest-access-field-label">Let anyone on my network view ARM without signing in (read-only)</span>
				<span class="field-help">Guests can see everything but change nothing. Off by default.</span>
			</span>
		</label>
	{:else}
		<div class="panel-section guest-access-field-row" data-testid="guest-access-row">
			<div class="field guest-access-field-info">
				<span class="field-label">Guest access</span>
				<p class="field-help">
					Let anyone on the network browse without signing in. Guests can view but not change anything.
				</p>
			</div>
			<div class="flex shrink-0 items-center gap-2">
				<span class="guest-access-field-state">{guest.disabled ? 'Off' : 'On'}</span>
				<Toggle checked={!guest.disabled} label="guest" onchange={toggle} disabled={saving} />
			</div>
		</div>
	{/if}
{/if}

<style>
	.guest-access-field {
		align-items: flex-start;
		gap: 0.625rem;
	}
	.guest-access-field input {
		margin-top: 0.25rem;
	}
	.guest-access-field-label {
		display: block;
		color: var(--color-text);
	}
	/* matches UsersCard's row chrome, which this row sits beside */
	.guest-access-field-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.625rem 0.75rem;
		border-color: var(--color-primary-tint-2);
		background: none;
	}
	.guest-access-field-info {
		min-width: 0;
		flex: 1 1 0%;
	}
	.guest-access-field-info .field-label {
		color: var(--color-text);
	}
	.guest-access-field-state {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
</style>
