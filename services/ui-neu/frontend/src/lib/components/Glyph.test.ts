import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, cleanup } from '$lib/test-utils';
import Glyph from './Glyph.svelte';

describe('Glyph', () => {
	afterEach(() => cleanup());

	it('renders the path for a named glyph', () => {
		const { container } = renderComponent(Glyph, { props: { name: 'check' } });
		const path = container.querySelector('svg path');
		expect(path).toHaveAttribute('d', 'M5 13l4 4L19 7');
	});

	it('renders the correct path per glyph name', () => {
		const cases: Array<[string, string]> = [
			['check', 'M5 13l4 4L19 7'],
			['check-circle', 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z'],
			['x', 'M6 18L18 6M6 6l12 12'],
			['x-circle', 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z'],
			['warning', 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z'],
			['clock', 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z'],
			['chevron-up', 'M5 15l7-7 7 7'],
			['chevron-down', 'M19 9l-7 7-7-7'],
			['chevron-right', 'M9 5l7 7-7 7'],
			['arrow-left', 'M10 19l-7-7m0 0l7-7m-7 7h18'],
			['arrow-right', 'M14 5l7 7m0 0l-7 7m7-7H3'],
			['info', 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'],
			['question-circle', 'M12 21a9 9 0 100-18 9 9 0 000 18zm-1-14a1 1 0 112 0 1 1 0 01-2 0zm0 3a1 1 0 011-1h0a1 1 0 011 1v4a1 1 0 11-2 0v-4z'],
			['shield-check', 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z'],
			['refresh', 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15'],
			['gear', 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z']
		];
		for (const [name, d] of cases) {
			const { container, unmount } = renderComponent(Glyph, { props: { name } });
			expect(container.querySelector('svg path')).toHaveAttribute('d', d);
			unmount();
		}
	});

	it('applies the default size class plus shrink-0', () => {
		const { container } = renderComponent(Glyph, { props: { name: 'check' } });
		const svg = container.querySelector('svg');
		expect(svg).toHaveClass('h-4', 'w-4', 'shrink-0');
	});

	it('appends a custom class alongside the defaults', () => {
		const { container } = renderComponent(Glyph, { props: { name: 'check', class: 'mx-auto h-3.5 w-3.5' } });
		const svg = container.querySelector('svg');
		expect(svg).toHaveClass('mx-auto', 'h-3.5', 'w-3.5', 'shrink-0');
	});

	it('sets the base svg attributes', () => {
		const { container } = renderComponent(Glyph, { props: { name: 'check' } });
		const svg = container.querySelector('svg');
		expect(svg).toHaveAttribute('fill', 'none');
		expect(svg).toHaveAttribute('stroke', 'currentColor');
		expect(svg).toHaveAttribute('viewBox', '0 0 24 24');
		const path = container.querySelector('svg path');
		expect(path).toHaveAttribute('stroke-width', '2');
		expect(path).toHaveAttribute('stroke-linecap', 'round');
		expect(path).toHaveAttribute('stroke-linejoin', 'round');
	});

	it('is aria-hidden by default with no label', () => {
		const { container } = renderComponent(Glyph, { props: { name: 'check' } });
		const svg = container.querySelector('svg');
		expect(svg).toHaveAttribute('aria-hidden', 'true');
		expect(svg).not.toHaveAttribute('role');
	});

	it('exposes role="img" and aria-label when label is given', () => {
		const { container } = renderComponent(Glyph, { props: { name: 'check', label: 'Success' } });
		const svg = container.querySelector('svg');
		expect(svg).toHaveAttribute('role', 'img');
		expect(svg).toHaveAttribute('aria-label', 'Success');
		expect(svg).not.toHaveAttribute('aria-hidden');
	});

	it('drops the default size when the caller sets one', () => {
		renderComponent(Glyph, { props: { name: 'check', class: 'h-3 w-3' } });
		const svg = document.querySelector('svg')!;
		expect(svg.classList.contains('h-3')).toBe(true);
		expect(svg.classList.contains('h-4')).toBe(false);
	});
});
