<script lang="ts">
	import { reveal } from '$lib/transitions';
	import { changePassword } from '$lib/api/auth';
	import Glyph from '$lib/components/Glyph.svelte';

	// Shared by /change-password, Settings > Users and the setup walkthrough's
	// first step. `currentPasswordDefault` hides the current-password field and
	// sends that value (first run: the seeded password is still "admin").
	// `hideSubmit` lets a parent drive submission through `submit()`.
	let {
		onsuccess,
		currentPasswordDefault,
		hideSubmit = false,
		onvalidchange
	}: {
		onsuccess: () => void;
		currentPasswordDefault?: string;
		hideSubmit?: boolean;
		/** Reports whether the form would submit, for a parent-owned Continue button. */
		onvalidchange?: (valid: boolean) => void;
	} = $props();

	const MIN_LENGTH = 8;

	let current = $state('');
	let next = $state('');
	let confirm = $state('');
	let error = $state('');
	let submitting = $state(false);
	let show = $state({ current: false, next: false, confirm: false });

	const uid = $props.id();
	const currentValue = $derived(currentPasswordDefault ?? current);
	const longEnough = $derived(next.length >= MIN_LENGTH);
	const matches = $derived(confirm.length > 0 && next === confirm);

	const valid = $derived(longEnough && matches && next !== currentValue);

	$effect(() => {
		onvalidchange?.(valid);
	});

	export function isValid(): boolean {
		return valid;
	}

	/** Validate and change the password. Resolves true on success. */
	export async function submit(): Promise<boolean> {
		if (submitting) return false;
		error = '';
		if (next === currentValue) {
			error = 'New password must differ from the current password';
			return false;
		}
		if (!longEnough) {
			error = `New password must be at least ${MIN_LENGTH} characters`;
			return false;
		}
		if (next !== confirm) {
			error = 'Passwords do not match';
			return false;
		}
		submitting = true;
		try {
			await changePassword(currentValue, next);
			onsuccess();
			return true;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Password change failed';
			return false;
		} finally {
			submitting = false;
		}
	}

	async function onSubmit(e: Event) {
		e.preventDefault();
		await submit();
	}
</script>

{#snippet passwordField(
	key: 'current' | 'next' | 'confirm',
	label: string,
	autocomplete: 'current-password' | 'new-password',
	describedby?: string
)}
	<div class="field">
		<label class="field-label" for="{uid}-{key}">{label}</label>
		<div class="change-password-form-row">
			{#if key === 'current'}
				<input
					id="{uid}-{key}"
					bind:value={current}
					type={show.current ? 'text' : 'password'}
					required
					{autocomplete}
				/>
			{:else if key === 'next'}
				<input
					id="{uid}-{key}"
					bind:value={next}
					type={show.next ? 'text' : 'password'}
					required
					{autocomplete}
					aria-describedby={describedby}
				/>
			{:else}
				<input
					id="{uid}-{key}"
					bind:value={confirm}
					type={show.confirm ? 'text' : 'password'}
					required
					{autocomplete}
					aria-describedby={describedby}
				/>
			{/if}
			<button
				type="button"
				class="btn btn-icon"
				aria-label="Show password"
				aria-pressed={show[key]}
				onclick={() => (show = { ...show, [key]: !show[key] })}
			>
				<Glyph name={show[key] ? 'eye-off' : 'eye'} />
			</button>
		</div>
	</div>
{/snippet}

<form onsubmit={onSubmit} class="panel change-password-form stack">
	<!-- Title lives in the route page -->

	{#if error}
		<p in:reveal class="alert alert-danger">{error}</p>
	{/if}
	{#if currentPasswordDefault === undefined}
		{@render passwordField('current', 'Current password', 'current-password')}
	{/if}
	{@render passwordField('next', 'New password', 'new-password', `${uid}-rule`)}
	<p id="{uid}-rule" class="change-password-form-check" data-met={longEnough}>
		<Glyph name={longEnough ? 'check' : 'x'} />
		<span>At least {MIN_LENGTH} characters<span class="sr-only"> ({longEnough ? 'met' : 'not met'})</span></span>
	</p>
	{@render passwordField('confirm', 'Confirm new password', 'new-password', `${uid}-match`)}
	{#if confirm.length > 0}
		<p id="{uid}-match" class="change-password-form-check" data-met={matches}>
			<Glyph name={matches ? 'check' : 'x'} />
			<span>{matches ? 'Passwords match' : "Passwords don't match"}</span>
		</p>
	{/if}
	{#if !hideSubmit}
		<button type="submit" disabled={submitting} class="btn btn-primary change-password-form-submit">
			{submitting ? 'Saving...' : 'Set new password'}
		</button>
	{/if}
</form>

<style>
	.change-password-form {
		width: 100%;
		max-width: 24rem;
		gap: 1rem;
	}
	.change-password-form-row {
		display: flex;
		gap: 0.5rem;
	}
	.change-password-form-row input {
		flex: 1 1 auto;
		min-width: 0;
	}
	.change-password-form-check {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		margin-top: -0.5rem;
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
	.change-password-form-check[data-met='true'] {
		color: var(--color-on-success-soft);
	}
	.change-password-form-submit {
		width: 100%;
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
</style>
