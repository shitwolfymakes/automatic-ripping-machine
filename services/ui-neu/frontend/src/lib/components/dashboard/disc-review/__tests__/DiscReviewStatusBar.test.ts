import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import DiscReviewStatusBar from '../DiscReviewStatusBar.svelte';

const START = '2025-06-15T12:00:00Z';

function baseProps(overrides: Record<string, unknown> = {}) {
	return {
		label: 'Waiting for review',
		waitStartTime: START,
		waitSeconds: 120,
		paused: false,
		held: null,
		...overrides
	};
}

describe('DiscReviewStatusBar', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2025-06-15T12:00:00Z'));
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it('shows the label text', () => {
		renderComponent(DiscReviewStatusBar, { props: baseProps({ label: 'Ready to rip' }) });
		expect(screen.getByText('Ready to rip')).toBeInTheDocument();
	});

	it('shows no countdown when waitStartTime is null', () => {
		renderComponent(DiscReviewStatusBar, { props: baseProps({ waitStartTime: null }) });
		expect(screen.queryByText('2m 00s')).not.toBeInTheDocument();
		expect(screen.queryByRole('button')).not.toBeInTheDocument();
	});

	it('shows no countdown when waitStartTime is undefined', () => {
		renderComponent(DiscReviewStatusBar, { props: baseProps({ waitStartTime: undefined }) });
		expect(screen.queryByText('2m 00s')).not.toBeInTheDocument();
		expect(screen.queryByRole('button')).not.toBeInTheDocument();
	});

	it('shows the countdown when waitStartTime is set', () => {
		renderComponent(DiscReviewStatusBar, { props: baseProps() });
		expect(screen.getByText('2m 00s')).toBeInTheDocument();
	});

	it('shows the countdown as paused when paused', () => {
		renderComponent(DiscReviewStatusBar, { props: baseProps({ paused: true }) });
		expect(screen.getByText('Paused')).toBeInTheDocument();
	});

	it('shows the hold reason and no control when held', () => {
		renderComponent(DiscReviewStatusBar, { props: baseProps({ held: 'Drive busy' }) });
		expect(screen.getByText('Drive busy')).toBeInTheDocument();
		expect(screen.queryByRole('button')).not.toBeInTheDocument();
	});

	it('calls onpause when the pause control is pressed', async () => {
		const onpause = vi.fn();
		const onresume = vi.fn();
		renderComponent(DiscReviewStatusBar, { props: baseProps({ onpause, onresume }) });
		await fireEvent.click(screen.getByRole('button', { name: 'Pause timer' }));
		expect(onpause).toHaveBeenCalledOnce();
		expect(onresume).not.toHaveBeenCalled();
	});

	it('calls onresume when the resume control is pressed', async () => {
		const onpause = vi.fn();
		const onresume = vi.fn();
		renderComponent(DiscReviewStatusBar, { props: baseProps({ paused: true, onpause, onresume }) });
		await fireEvent.click(screen.getByRole('button', { name: 'Resume timer' }));
		expect(onresume).toHaveBeenCalledOnce();
		expect(onpause).not.toHaveBeenCalled();
	});

	it('does nothing when the control is pressed without handlers', async () => {
		renderComponent(DiscReviewStatusBar, { props: baseProps() });
		await fireEvent.click(screen.getByRole('button', { name: 'Pause timer' }));
		cleanup();
		renderComponent(DiscReviewStatusBar, { props: baseProps({ paused: true }) });
		await fireEvent.click(screen.getByRole('button', { name: 'Resume timer' }));
		expect(screen.getByText('Paused')).toBeInTheDocument();
	});
});
