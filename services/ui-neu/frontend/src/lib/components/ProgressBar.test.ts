import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import ProgressBar from './ProgressBar.svelte';

describe('ProgressBar', () => {
	afterEach(() => cleanup());

	describe('rendering', () => {
		it('renders with a percentage label by default', () => {
			renderComponent(ProgressBar, { props: { value: 50 } });
			expect(screen.getByText('50%')).toBeInTheDocument();
		});

		it('hides label when showLabel is false', () => {
			renderComponent(ProgressBar, { props: { value: 50, showLabel: false } });
			expect(screen.queryByText('50%')).not.toBeInTheDocument();
		});
	});

	describe('props', () => {
		it('calculates percentage from value and max', () => {
			renderComponent(ProgressBar, { props: { value: 25, max: 50 } });
			expect(screen.getByText('50%')).toBeInTheDocument();
		});

		it('clamps percentage to 100', () => {
			renderComponent(ProgressBar, { props: { value: 150 } });
			expect(screen.getByText('100%')).toBeInTheDocument();
		});

		it('clamps percentage to 0', () => {
			renderComponent(ProgressBar, { props: { value: -10 } });
			expect(screen.getByText('0%')).toBeInTheDocument();
		});

		it('applies a custom colorVar as the --progress-color custom property', () => {
			const { container } = renderComponent(ProgressBar, {
				props: { value: 50, colorVar: 'var(--color-status-error)' }
			});
			const fill = container.querySelector('[data-progress-fill]') as HTMLElement;
			expect(fill.style.getPropertyValue('--progress-color')).toBe('var(--color-status-error)');
		});

		it('sets the --progress custom property based on percentage', () => {
			const { container } = renderComponent(ProgressBar, { props: { value: 75 } });
			const fill = container.querySelector('[data-progress-fill]') as HTMLElement;
			expect(fill.style.getPropertyValue('--progress')).toBe('75%');
		});
	});
});
