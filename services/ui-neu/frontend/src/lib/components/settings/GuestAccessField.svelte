<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import Toggle from '$lib/components/notifications/Toggle.svelte';
	import { setUserDisabled } from '$lib/api/users';
	import type { UserView } from '$lib/types/api.gen';

	// Guest access on/off for Settings > Users: an immediate-effect Toggle.
	// The parent passes the guest account, or null when there is none.
	let {
		guest,
		onsaved,
		onerror
	}: {
		guest: UserView | null;
		onsaved?: (enabled: boolean) => void;
		onerror?: (message: string) => void;
	} = $props();

	let saving = $state(false);

	async function toggle(user: UserView, next: boolean): Promise<void> {
		saving = true;
		try {
			await setUserDisabled(user.id, !next);
			onsaved?.(next);
		} catch (e) {
			const message = errorMessage(e, 'Failed to update guest access');
			onerror?.(message);
		} finally {
			saving = false;
		}
	}
</script>

{#if guest}
	<div class="panel-section guest-access-field-row" data-testid="guest-access-row">
		<div class="field guest-access-field-info">
			<span class="field-label">Guest access</span>
			<p class="field-help">
				Let anyone on the network browse without signing in. Guests can view but not change anything.
			</p>
		</div>
		<div class="flex shrink-0 items-center gap-2">
			<span class="guest-access-field-state">{guest.disabled ? 'Off' : 'On'}</span>
			<Toggle checked={!guest.disabled} label="guest" onchange={(next) => toggle(guest, next)} disabled={saving} />
		</div>
	</div>
{/if}

<style>
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
