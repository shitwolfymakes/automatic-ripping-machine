import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import SetupFooter from '../SetupFooter.svelte';
import { STEPS } from '../steps';

const handlers = () => ({ onback: vi.fn(), onskip: vi.fn(), oncontinue: vi.fn() });

describe('SetupFooter', () => {
	afterEach(() => cleanup());

	it('step 1: no Back, no Skip, Continue blocked with the reason', () => {
		renderComponent(SetupFooter, {
			props: {
				step: STEPS[0],
				first: true,
				last: false,
				canContinue: false,
				blockedReason: 'Set a password first.',
				...handlers()
			}
		});
		expect(screen.queryByRole('button', { name: /back/i })).toBeNull();
		expect(screen.queryByRole('button', { name: /skip/i })).toBeNull();
		expect(screen.getByRole('button', { name: /continue/i })).toBeDisabled();
		expect(screen.getByText('Set a password first.')).toBeInTheDocument();
	});

	it('optional step: Skip for now; save hint per step', async () => {
		const h = handlers();
		renderComponent(SetupFooter, { props: { step: STEPS[4], first: false, last: false, ...h } });
		expect(screen.getByText('Saved when you press Continue.')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: /skip for now/i }));
		expect(h.onskip).toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: /back/i }));
		expect(h.onback).toHaveBeenCalled();
	});

	it('live step and last step', () => {
		renderComponent(SetupFooter, { props: { step: STEPS[2], first: false, last: false, ...handlers() } });
		expect(screen.getByText('Changes on this step save as you make them.')).toBeInTheDocument();
		cleanup();
		renderComponent(SetupFooter, { props: { step: STEPS[8], first: false, last: true, ...handlers() } });
		expect(screen.getByRole('button', { name: /go to dashboard/i })).toBeInTheDocument();
	});
});
