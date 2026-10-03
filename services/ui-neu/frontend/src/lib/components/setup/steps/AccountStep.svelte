<script lang="ts">
	import { onMount } from 'svelte';
	import type { SetupView, SystemResourcesResponse } from '$lib/types/api.gen';
	import ChangePasswordForm from '$lib/components/settings/ChangePasswordForm.svelte';
	import { fetchResources } from '$lib/api/resources';
	import { fetchSystemVersion } from '$lib/api/system';
	import { clearPasswordMustChange } from '$lib/stores/auth';
	import type { StepCommitResult } from '../steps';

	// Step 1, the one hard gate: ARM locks everything else until the seeded
	// admin password is changed (setup spec §5.2).
	let { view, setBlocked }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();

	let version = $state<string | null>(null);
	let resources = $state<SystemResourcesResponse | null>(null);
	let pw: ChangePasswordForm | undefined = $state();

	const mediaFree = $derived(resources?.storage.find((r) => r.name === 'MEDIA_ROOT')?.free_gb ?? null);

	onMount(async () => {
		if (view.admin_default_password) setBlocked?.('Set a password that meets the rule to continue.');
		const [v, r] = await Promise.allSettled([fetchSystemVersion(), fetchResources()]);
		if (v.status === 'fulfilled') version = v.value.version;
		if (r.status === 'fulfilled') resources = r.value;
	});

	function onValid(valid: boolean) {
		if (view.admin_default_password) setBlocked?.(valid ? null : 'Set a password that meets the rule to continue.');
	}

	export async function commit(): Promise<StepCommitResult> {
		if (view.admin_default_password) {
			if (!pw || !(await pw.submit())) return false;
		}
		return 'done';
	}
</script>

<div class="stack stack-lg">
	<section class="panel account-step-welcome">
		<p class="account-step-hello">Welcome to ARM{version ? ` ${version}` : ''}.</p>
		<dl class="account-step-facts">
			<div>
				<dt>CPU</dt>
				<dd>{resources ? `${Math.round(resources.cpu_percent)}% busy` : '...'}</dd>
			</div>
			<div>
				<dt>Memory</dt>
				<dd>{resources ? `${resources.memory.total_gb.toFixed(1)} GB` : '...'}</dd>
			</div>
			<div>
				<dt>Media drive</dt>
				<dd>{mediaFree !== null ? `${Math.round(mediaFree)} GB free` : 'Measuring...'}</dd>
			</div>
		</dl>
	</section>

	<section class="panel stack">
		<h2 class="account-step-title">Admin password</h2>
		{#if view.admin_default_password}
			<p class="account-step-help">
				You signed in with the first-boot password. Choose your own; you'll use it from now on.
			</p>
			<div class="account-step-password">
				<ChangePasswordForm
					bind:this={pw}
					currentPasswordDefault="admin"
					hideSubmit
					onsuccess={clearPasswordMustChange}
					onvalidchange={onValid}
				/>
			</div>
		{:else}
			<p class="account-step-help">Your admin password is already set. Change it any time in Settings, Users.</p>
		{/if}
	</section>
</div>

<style>
	.account-step-hello {
		font-weight: 600;
	}
	.account-step-facts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
		gap: 0.75rem;
		margin-top: 0.75rem;
	}
	.account-step-facts dt {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--color-text-faint);
	}
	.account-step-facts dd {
		margin: 0;
		color: var(--color-text);
	}
	.account-step-title {
		font-size: 1.0625rem;
		font-weight: 600;
	}
	.account-step-help {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.account-step-welcome {
		padding: 1rem 1.25rem;
	}
	/* :global: the shared password form caps itself at 24rem for Settings; here it fills the panel */
	.account-step-password :global(.change-password-form) {
		max-width: none;
	}
</style>
