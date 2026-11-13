import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import SetupFooter from '../SetupFooter.svelte';
import { STEPS } from '../../../setup/steps';

// Branch pins for SetupFooter, beside SetupFooter.test.ts. No branch is left
// open.

describe('SetupFooter branches', () => {
	afterEach(() => cleanup());

	it('draws Skip for now as a plain button on the notifications step', () => {
		const step = STEPS.find((s) => s.id === 'notifications');
		if (!step) throw new Error('no notifications step');
		renderComponent(SetupFooter, {
			props: { step, first: false, last: false, onback: vi.fn(), onskip: vi.fn(), oncontinue: vi.fn() }
		});
		// The class is the whole of what differs from the link-style Skip.
		expect(screen.getByRole('button', { name: /skip for now/i })).not.toHaveClass('btn-link');
	});
});
