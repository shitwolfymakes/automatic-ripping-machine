<script lang="ts">
	import { goto } from '$app/navigation';
	import { panel } from '$lib/transitions';
	import { clearPasswordMustChange } from '$lib/stores/auth';
	import ChangePasswordForm from '$lib/components/settings/ChangePasswordForm.svelte';

	function onsuccess() {
		clearPasswordMustChange();
		goto('/');
	}
</script>

<div in:panel class="flex min-h-screen items-center justify-center p-4">
	<div class="w-full max-w-sm">
		<h1 class="text-lg font-semibold">Change your password</h1>
		<p class="mb-6 text-sm text-gray-600 dark:text-gray-300">You must set a new password before continuing.</p>
		<ChangePasswordForm {onsuccess} />
	</div>
</div>
