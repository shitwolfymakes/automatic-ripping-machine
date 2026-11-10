<script lang="ts">
	import { saveControl } from './setup-config-fields-control';

	// Stand-in for SetupConfigFields whose save() result a test controls.
	let { step }: { step: string } = $props();
	void step;

	export async function save(): Promise<boolean> {
		return saveControl.result;
	}
</script>
