<script lang="ts">
	import type { ConfigView } from '$lib/types/api.gen';
	import { stubState } from './setup-config-fields-stub';

	// Stand-in for SetupConfigFields: the step under test only calls these.
	let { step }: { step: string } = $props();
	void step;

	export async function save(): Promise<boolean> {
		return true;
	}
	export function current(): ConfigView | null {
		return stubState.atMount;
	}
	export async function refresh(): Promise<ConfigView | null> {
		return stubState.afterSave;
	}
</script>
