<script lang="ts">
	import type { SetupView, SystemDiagnosticsResponse } from '$lib/types/api.gen';
	import SystemHealth from '$lib/components/shared/SystemHealth.svelte';
	import { SYSTEM_STEP_CHECKS } from '$lib/dashboard/system-health';
	import type { StepCommitResult } from '../../../setup/steps';

	// Step 2: deploy-time facts the operator can't change in the browser. Never
	// blocks; problems record the step as needing attention.
	let { view }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();
	void view;

	let result = $state<SystemDiagnosticsResponse | null>(null);

	export async function commit(): Promise<StepCommitResult> {
		if (!result) return 'attention';
		const ok = result.checks.every((c) => !SYSTEM_STEP_CHECKS.has(c.name) || c.status === 'ok');
		return ok ? 'done' : 'attention';
	}
</script>

<SystemHealth autorun grouped scope="system" onresult={(r) => (result = r)} />
