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
	<ChangePasswordForm {onsuccess} />
</div>
