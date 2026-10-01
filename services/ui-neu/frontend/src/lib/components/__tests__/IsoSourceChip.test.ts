import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, cleanup } from '$lib/test-utils';
import IsoSourceChip from '../IsoSourceChip.svelte';

const LONG_NAME = 'The_Grand_Budapest_Hotel_2014_BLURAY_Criterion_Collection_Disc_1.iso';

describe('IsoSourceChip', () => {
	afterEach(() => cleanup());

	it('labels the chip and keeps the full name in the title', () => {
		const { container } = renderComponent(IsoSourceChip, { props: { name: LONG_NAME } });
		const root = container.querySelector('.chip')!;
		expect(root).toHaveAttribute('title', LONG_NAME);
		expect(root).toHaveAttribute('aria-label', `ISO file ${LONG_NAME}`);
	});

	it('renders the chip-info chip-sm block classes', () => {
		const { container } = renderComponent(IsoSourceChip, { props: { name: 'a.iso' } });
		const root = container.querySelector('.chip')!;
		expect(root).toHaveClass('chip', 'chip-info', 'chip-sm');
	});

	it('shows the ISO lead segment', () => {
		const { getByText } = renderComponent(IsoSourceChip, { props: { name: 'a.iso' } });
		expect(getByText('ISO')).toBeInTheDocument();
	});

	it('renders both a desktop (36 char) and mobile (26 char) truncation, CSS-toggled', () => {
		const { container } = renderComponent(IsoSourceChip, { props: { name: LONG_NAME } });
		const desktop = container.querySelector('.iso-source-chip-name-desktop')!;
		const mobile = container.querySelector('.iso-source-chip-name-mobile')!;
		expect(desktop.textContent?.length).toBe(36);
		expect(mobile.textContent?.length).toBe(26);
		expect(desktop.textContent?.endsWith('Disc_1.iso')).toBe(true);
		expect(mobile.textContent?.endsWith('Disc_1.iso')).toBe(true);
	});

	it('keeps a short name unchanged in both spans', () => {
		const { container } = renderComponent(IsoSourceChip, { props: { name: 'a.iso' } });
		const desktop = container.querySelector('.iso-source-chip-name-desktop')!;
		const mobile = container.querySelector('.iso-source-chip-name-mobile')!;
		expect(desktop.textContent).toBe('a.iso');
		expect(mobile.textContent).toBe('a.iso');
	});
});
