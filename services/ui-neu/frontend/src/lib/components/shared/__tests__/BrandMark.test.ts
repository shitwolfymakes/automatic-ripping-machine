// Open arm the coverage tool reports that is Svelte's, not the component's:
// the class attribute's `{className}` compiles to `(...) ?? ''`, and
// `className` defaults to an empty string.
import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, cleanup } from '$lib/testing/render';
import BrandMark from '../BrandMark.svelte';
import { BRAND_MARK_PATHS } from '../../../ui/brand-marks';

describe('BrandMark', () => {
	afterEach(() => cleanup());

	it('draws the named mark filled, hidden from assistive technology', () => {
		const { container } = renderComponent(BrandMark, { props: { name: 'github', class: 'extra' } });
		const svg = container.querySelector('svg') as SVGElement;
		expect(svg.getAttribute('fill')).toBe('currentColor');
		expect(svg.getAttribute('aria-hidden')).toBe('true');
		expect(svg.getAttribute('class')).toContain('extra');
		expect(svg.querySelector('path')?.getAttribute('d')).toBe(BRAND_MARK_PATHS.github);
	});

	it('works without a class', () => {
		const { container } = renderComponent(BrandMark, { props: { name: 'github' } });
		expect(container.querySelector('svg')).not.toBeNull();
	});
});
