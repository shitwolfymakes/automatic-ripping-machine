<script lang="ts">
	import { goto } from '$app/navigation';
	import { clearPasswordMustChange } from '$lib/stores/auth';
	import ChangePasswordForm from '$lib/components/settings/ChangePasswordForm.svelte';

	function onsuccess() {
		clearPasswordMustChange();
		goto('/');
	}
</script>

<div class="change-password-page">
	<div class="change-password-page-inner">
		<h1 class="change-password-page-title">Change your password</h1>
		<p class="change-password-page-hint">You must set a new password before continuing.</p>
		<ChangePasswordForm {onsuccess} />
	</div>
</div>

<style>
	/* full-viewport centering wrapper; not a block, this page's own shell */
	.change-password-page { display: flex; min-height: 100vh; align-items: center; justify-content: center; padding: 1rem; }
	.change-password-page-inner { width: 100%; max-width: 24rem; }
	.change-password-page-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	.change-password-page-hint { margin-bottom: 1.5rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-secondary); }
</style>
