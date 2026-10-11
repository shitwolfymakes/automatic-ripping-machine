<script lang="ts">
	import type { SetupView } from '$lib/types/api.gen';
	import SetupConfigFields from '../SetupConfigFields.svelte';
	import type { StepCommitResult } from '../steps';

	// Step 4: which MakeMKV key, and Blu-ray decryption data. Comes after
	// Drives because only a running ripper can verify the key (setup spec §5.5).
	let { view }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();
	void view;
	let fields: SetupConfigFields | undefined = $state();

	export async function commit(): Promise<StepCommitResult> {
		if (!fields || !(await fields.save())) return false;
		return fields.current()?.makemkv_key_valid === false ? 'attention' : 'done';
	}
</script>

<SetupConfigFields bind:this={fields} step="makemkv" />
