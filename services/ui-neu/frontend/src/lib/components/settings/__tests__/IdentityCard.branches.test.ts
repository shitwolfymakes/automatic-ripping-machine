import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/testing/render';
import IdentityCardHarness from './IdentityCardHarness.svelte';
import { IDENTITY_METAS, IDENTITY_DEFAULTS } from '$lib/__fixtures__/identity-metas';

// Branch pins for IdentityCard, beside IdentityCard.test.ts. No branch is
// left open.

afterEach(() => cleanup());

const render = (fields = IDENTITY_METAS) =>
	renderComponent(IdentityCardHarness, { props: { initial: { ...IDENTITY_DEFAULTS }, fields } });
const valuesOf = (component: unknown) => (component as { getValues: () => Record<string, unknown> }).getValues();
const without = (key: string) => IDENTITY_METAS.filter((f) => f.key !== key);

describe('IdentityCard', () => {
	it('unticking the TheDiscDB checkbox writes thediscdb_enabled', async () => {
		const { component } = render();
		await fireEvent.click(screen.getByRole('checkbox', { name: 'TheDiscDB disc map' }));
		expect(valuesOf(component).thediscdb_enabled).toBe(false);
		await fireEvent.click(screen.getByRole('checkbox', { name: 'TheDiscDB disc map' }));
		expect(valuesOf(component).thediscdb_enabled).toBe(true);
	});

	it('typing in the tolerance field writes episode_match_tolerance_seconds', async () => {
		const { component } = render();
		const box = screen.getByRole('spinbutton', { name: 'Episode match tolerance (seconds)' });
		await fireEvent.input(box, { target: { value: '120' } });
		expect(valuesOf(component).episode_match_tolerance_seconds).toBe(120);
	});

	it('draws no box for a source list whose field is missing', () => {
		render(without('movie_sources'));
		expect(screen.queryByRole('list', { name: 'Movie sources' })).toBeNull();
		expect(screen.queryByRole('heading', { name: 'Movies', level: 5 })).toBeNull();
		expect(screen.getByRole('heading', { name: 'TV shows', level: 5 })).toBeInTheDocument();
		expect(screen.getByRole('list', { name: 'Episode sources' })).toBeInTheDocument();
	});

	it('draws no Advanced step without a disc_hint_sources field', () => {
		render(without('disc_hint_sources'));
		expect(screen.queryByText('Advanced')).toBeNull();
		expect(screen.queryByRole('checkbox', { name: 'Ignore the volume label' })).toBeNull();
	});
});
