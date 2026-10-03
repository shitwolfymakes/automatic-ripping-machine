<script lang="ts">
	import type { SetupView, SystemDiagnosticsResponse } from '$lib/types/api.gen';
	import SystemHealth from '$lib/components/settings/SystemHealth.svelte';
	import type { StepCommitResult } from '../steps';

	// Step 2: deploy-time facts the operator can't change in the browser. Never
	// blocks; problems record the step as needing attention (setup spec §5.3).
	let { view }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();
	void view;

	// Same set the backend reconciles on (routers/setup.py _SYSTEM_STEP_CHECKS).
	const SYSTEM_STEP_CHECKS = new Set(['config', 'MEDIA_ROOT', 'RAW_ROOT', 'LOG_DIR', 'ripper_manager', 'transcoder']);
	let result = $state<SystemDiagnosticsResponse | null>(null);

	export async function commit(): Promise<StepCommitResult> {
		if (!result) return 'attention';
		const ok = result.checks.every((c) => !SYSTEM_STEP_CHECKS.has(c.name) || c.status === 'ok');
		return ok ? 'done' : 'attention';
	}
</script>

<SystemHealth autorun grouped scope="system" onresult={(r) => (result = r)} />
