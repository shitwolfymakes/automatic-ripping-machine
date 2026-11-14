import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, cleanup } from '$lib/testing/render';
import MatchGlyph from '../MatchGlyph.svelte';

describe('MatchGlyph', () => {
	afterEach(() => cleanup());

	it('draws the check glyph for a match', () => {
		const { container } = renderComponent(MatchGlyph, { props: { kind: 'match' } });
		expect(container.querySelector('svg path')).toHaveAttribute('d', 'M5 13l4 4L19 7');
	});

	it('draws the x glyph for a mismatch', () => {
		const { container } = renderComponent(MatchGlyph, { props: { kind: 'mismatch' } });
		expect(container.querySelector('svg path')).toHaveAttribute('d', 'M6 18L18 6M6 6l12 12');
	});

	it('draws a tilde for a close match', () => {
		const { container } = renderComponent(MatchGlyph, { props: { kind: 'close' } });
		expect(container.querySelector('svg')).toBeNull();
		expect(container.textContent?.trim()).toBe('~');
	});

	it('draws a dash for an unknown match', () => {
		const { container } = renderComponent(MatchGlyph, { props: { kind: 'unknown' } });
		expect(container.querySelector('svg')).toBeNull();
		expect(container.textContent?.trim()).toBe('-');
	});
});
