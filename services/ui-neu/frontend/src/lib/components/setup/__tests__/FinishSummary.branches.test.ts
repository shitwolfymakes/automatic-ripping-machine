import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import type { SetupView } from '$lib/types/api.gen';
import FinishSummary from '../FinishSummary.svelte';

// Branch pins for FinishSummary, beside FinishSummary.test.ts. No branch is
// left open.

const view: SetupView = {
	completed_at: null,
	current_step: 'finish',
	admin_default_password: false,
	checklist_dismissed: false,
	progress: {}
};

describe('FinishSummary branches', () => {
	afterEach(() => cleanup());

	it('shows only the label on a row when no summaries are given', () => {
		renderComponent(FinishSummary, { props: { view } });
		const row = screen.getByTestId('finish-row-drives');
		expect(row).toHaveTextContent('Not done');
		expect(row).toHaveTextContent('Drives');
		expect(row).not.toHaveTextContent('enrolled');
	});
});
