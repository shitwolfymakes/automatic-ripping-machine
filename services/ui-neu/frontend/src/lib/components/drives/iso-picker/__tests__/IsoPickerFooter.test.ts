import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import IsoPickerFooter from '../IsoPickerFooter.svelte';

function renderFooter(overrides: Record<string, unknown> = {}) {
	const onclose = vi.fn();
	const onstart = vi.fn();
	renderComponent(IsoPickerFooter, {
		notConfigured: false,
		isFolderMode: false,
		selectedName: null,
		selectedPath: null,
		starting: false,
		onclose,
		onstart,
		...overrides
	});
	return { onclose, onstart };
}

describe('IsoPickerFooter', () => {
	afterEach(() => cleanup());

	describe('when the library is not configured', () => {
		it('shows the setup helper and only a Close button', () => {
			renderFooter({ notConfigured: true });
			expect(screen.getByText('Nothing to pick until the library is set up.')).toBeInTheDocument();
			expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
			expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
			expect(screen.queryByRole('button', { name: 'Start rip' })).not.toBeInTheDocument();
		});

		it('calls onclose when Close is clicked', async () => {
			const { onclose } = renderFooter({ notConfigured: true });
			await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
			expect(onclose).toHaveBeenCalledOnce();
		});
	});

	describe('when the library is configured', () => {
		it('shows the selected name in the helper', () => {
			renderFooter({ selectedName: 'movie.iso' });
			expect(screen.getByText('Selected: movie.iso')).toBeInTheDocument();
		});

		it('prompts for an ISO when nothing is selected', () => {
			renderFooter();
			expect(screen.getByText('Pick an ISO to start.')).toBeInTheDocument();
		});

		it('prompts for a disc folder in folder mode when nothing is selected', () => {
			renderFooter({ isFolderMode: true });
			expect(screen.getByText('Pick a disc folder to start.')).toBeInTheDocument();
		});

		it('calls onclose when Cancel is clicked', async () => {
			const { onclose } = renderFooter();
			const cancel = screen.getByRole('button', { name: 'Cancel' });
			expect(cancel).toBeEnabled();
			await fireEvent.click(cancel);
			expect(onclose).toHaveBeenCalledOnce();
		});

		it('disables Cancel while starting', () => {
			renderFooter({ starting: true });
			expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
		});

		it('disables Start without a selected path', () => {
			renderFooter();
			expect(screen.getByRole('button', { name: 'Start rip' })).toBeDisabled();
		});

		it('disables Start while starting and reads Starting...', () => {
			renderFooter({ selectedPath: '/lib/a.iso', starting: true });
			expect(screen.getByRole('button', { name: 'Starting...' })).toBeDisabled();
		});

		it('enables Start with a selected path and calls onstart', async () => {
			const { onstart } = renderFooter({ selectedPath: '/lib/a.iso' });
			const start = screen.getByRole('button', { name: 'Start rip' });
			expect(start).toBeEnabled();
			await fireEvent.click(start);
			expect(onstart).toHaveBeenCalledOnce();
		});
	});
});
