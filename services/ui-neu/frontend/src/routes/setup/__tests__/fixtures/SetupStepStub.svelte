<script lang="ts">
	import type { SetupView } from '$lib/types/api.gen';
	import type { StepCommitResult } from '$lib/setup/steps';
	import { stubState } from './setup-step-stub';

	// Stand-in for the page's nine step components: the page only passes these
	// props and calls commit().
	let { view, setBlocked }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();
	void view;
	stubState.setBlocked = setBlocked;

	export function commit(): Promise<StepCommitResult> {
		return stubState.commit();
	}
</script>

<div data-testid="step-stub">step stub</div>
