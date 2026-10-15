import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, within } from '$lib/test-utils';
import IdentityCardHarness from './IdentityCardHarness.svelte';
import { IDENTITY_METAS, IDENTITY_DEFAULTS } from '$lib/utils/__tests__/fixtures/identity-metas';

afterEach(() => cleanup());

const render = (props: Record<string, unknown> = {}) =>
	renderComponent(IdentityCardHarness, {
		props: { initial: { ...IDENTITY_DEFAULTS }, fields: IDENTITY_METAS, ...props }
	});
const step = (n: number) => document.querySelector(`.identity-card-step[data-step="${n}"]`) as HTMLElement;
const strip = () => screen.getByRole('group', { name: 'Identity summary' });

describe('IdentityCard', () => {
	it('renders the card root and the Disc kind radiogroup with Blu-ray checked', () => {
		render();
		expect(screen.getByTestId('identity-card')).toBeInTheDocument();
		const group = screen.getByRole('radiogroup', { name: 'Disc kind' });
		const radios = within(group).getAllByRole('radio');
		expect(radios.map((r) => r.textContent?.trim())).toEqual(['Blu-ray', 'DVD', 'CD']);
		expect(within(group).getByRole('radio', { name: 'Blu-ray' })).toHaveAttribute('aria-checked', 'true');
		expect(within(group).getByRole('radio', { name: 'CD' })).toHaveAttribute('aria-checked', 'false');
	});

	it('clicking CD switches the strip to the CD view', async () => {
		render();
		expect(strip()).toHaveTextContent('Movies: TMDb, OMDb · TV shows: TMDb, TVmaze, TVDB');
		await fireEvent.click(screen.getByRole('radio', { name: 'CD' }));
		expect(screen.getByRole('radio', { name: 'CD' })).toHaveAttribute('aria-checked', 'true');
		expect(strip()).toHaveTextContent('Music: MusicBrainz');
		expect(strip()).toHaveTextContent('Not used for CDs');
	});

	it('Step 1 lists the four disc rows with their chips and no controls', () => {
		render();
		const s1 = step(1);
		expect(within(s1).getByRole('heading', { name: 'Step 1 · On the disc' })).toBeInTheDocument();
		const rows = within(s1).getAllByTestId(/^identity-row-/);
		expect(rows.map((r) => r.querySelector('.identity-card-row-name')?.textContent?.trim())).toEqual([
			'Disc title metadata',
			'Volume label',
			'Disc ID (track layout)',
			'CD-TEXT'
		]);
		const chips = (r: HTMLElement) => Array.from(r.querySelectorAll('.chip')).map((c) => c.textContent?.trim());
		expect(chips(rows[0])).toEqual(['Blu-ray', 'UHD']);
		expect(chips(rows[1])).toEqual(['All discs']);
		expect(chips(rows[2])).toEqual(['CD']);
		expect(chips(rows[3])).toEqual(['CD', 'Planned']);
		expect(rows[3]).toHaveAttribute('aria-disabled', 'true');
		expect(rows[3]).toHaveTextContent('Album, artist and track names. Not built yet.');
		expect(s1.querySelectorAll('input, select, button')).toHaveLength(0);
		expect(s1).toHaveTextContent(
			"ARM reads all of these. When they disagree, the disc's own metadata beats its label."
		);
	});

	it('Step 2 has the two disc database checkboxes with their chips and descriptions', () => {
		render();
		const s2 = step(2);
		expect(within(s2).getByRole('heading', { name: 'Step 2 · Disc database' })).toBeInTheDocument();
		const discdb = within(s2).getByRole('checkbox', { name: 'TheDiscDB disc map' });
		expect(discdb).toBeChecked();
		expect(within(s2).getByRole('checkbox', { name: 'ARM community database (CRC64)' })).toBeChecked();
		const chips = (key: string) =>
			Array.from(s2.querySelectorAll(`#setting-${key} .chip`)).map((c) => c.textContent?.trim());
		expect(chips('thediscdb_enabled')).toEqual(['Blu-ray', 'UHD', 'DVD']);
		expect(chips('crc64service_enabled')).toEqual(['DVD']);
		expect(discdb).toHaveAccessibleDescription(
			"Matches the disc itself and names its titles before any online lookup. When it matches, it wins over the disc's labels, and ARM confirms the title with the first online source below."
		);
		expect(within(s2).getByRole('checkbox', { name: 'ARM community database (CRC64)' })).toHaveAccessibleDescription(
			"Send a DVD's CRC64 fingerprint to the ARM project's community database and take its title when it has one. DVDs only; no key needed."
		);
	});

	it('Step 3 shows the three ranked lists, the tolerance under TV and the planned CDDB row', () => {
		render();
		const s3 = step(3);
		expect(within(s3).getByRole('heading', { name: 'Step 3 · Online lookup' })).toBeInTheDocument();
		expect(s3).toHaveTextContent('Tried top to bottom; the first confident match wins.');
		for (const name of ['Movie sources', 'Episode sources', 'Music sources']) {
			expect(within(s3).getByRole('list', { name })).toBeInTheDocument();
		}
		expect(within(s3).getAllByText('Rank 1')).toHaveLength(3);
		expect(screen.getAllByText('Rank 1')).toHaveLength(3);
		const tv = s3.querySelector('#setting-episode_sources') as HTMLElement;
		expect(within(tv).getByRole('heading', { name: 'TV shows' })).toBeInTheDocument();
		expect(within(tv).getByRole('spinbutton', { name: 'Match tolerance (seconds)' })).toHaveValue(300);
		const music = s3.querySelector('#setting-music_sources') as HTMLElement;
		const cddb = within(music).getByTestId('identity-cddb');
		expect(cddb).toHaveAttribute('aria-disabled', 'true');
		expect(cddb).toHaveTextContent('CDDB');
		expect(cddb).toHaveTextContent('Planned');
		expect(cddb).toHaveTextContent('Not built yet, so never ranked');
		expect(s3).not.toHaveTextContent('No sources on');
	});

	it('an empty list shows No sources on under its heading', () => {
		render({ initial: { ...IDENTITY_DEFAULTS, music_sources: [] } });
		const music = step(3).querySelector('#setting-music_sources') as HTMLElement;
		expect(music).toHaveTextContent('No sources on');
	});

	it('Step 4 has Movies / TV shows / Music checkboxes under the caption, bound to the auto-apply fields', async () => {
		const { component } = render();
		const s4 = step(4);
		expect(within(s4).getByRole('heading', { name: 'Step 4 · Trust' })).toBeInTheDocument();
		const group = within(s4).getByRole('group', { name: 'Apply confident matches' });
		expect(
			within(group)
				.getAllByRole('checkbox')
				.map((c) => c.getAttribute('aria-label'))
		).toEqual(['Movies', 'TV shows', 'Music']);
		expect(s4).toHaveTextContent(
			'When off, a match waits on the job page for you to confirm it and the disc is held with no countdown. Ripping › Review first still holds every disc.'
		);
		await fireEvent.click(within(group).getByRole('checkbox', { name: 'Movies' }));
		expect((component as unknown as { getValues: () => Record<string, unknown> }).getValues().movie_auto_apply).toBe(
			false
		);
		expect(strip()).toHaveTextContent('Movies: Waits for review · TV shows: Apply confident matches');
	});

	it('Advanced: ignoring the volume label marks its Step 1 row and drops it from disc_hint_sources', async () => {
		const { component } = render();
		const getValues = (component as unknown as { getValues: () => Record<string, unknown> }).getValues;
		expect(screen.getByText('Advanced')).toBeInTheDocument();
		const row = screen.getByTestId('identity-row-label');
		expect(row).not.toHaveTextContent('Ignored (see Advanced)');

		await fireEvent.click(screen.getByRole('checkbox', { name: 'Ignore the volume label' }));
		expect(row).toHaveTextContent('Ignored (see Advanced)');
		expect(getValues().disc_hint_sources).toEqual(['bd_title']);
		expect(screen.getByTestId('identity-row-bd_title')).not.toHaveTextContent('Ignored (see Advanced)');

		await fireEvent.click(screen.getByRole('checkbox', { name: 'Ignore the volume label' }));
		expect(getValues().disc_hint_sources).toEqual(['bd_title', 'label']);
		expect(screen.getByRole('checkbox', { name: 'Ignore the disc title metadata' })).not.toBeChecked();
		expect(screen.getByTestId('identity-card')).toHaveTextContent(
			"For collections where the disc's own text is usually wrong. Fix a single disc from its job page instead. With the volume label ignored, a DVD with no disc title metadata gets no automatic title search."
		);
	});

	it('disabled renders every control disabled; the segmented control stays usable', async () => {
		render({ disabled: true });
		const card = screen.getByTestId('identity-card');
		const radios = within(card).getAllByRole('radio');
		const controls = Array.from(card.querySelectorAll('input, select, button')).filter(
			(el) => !radios.includes(el as HTMLElement)
		);
		expect(controls.length).toBeGreaterThan(10);
		for (const el of controls) expect(el).toBeDisabled();
		for (const r of radios) expect(r).toBeEnabled();
		await fireEvent.click(screen.getByRole('radio', { name: 'DVD' }));
		expect(strip()).toHaveTextContent('ARM community database (CRC64)');
	});

	it('skips a control whose meta is missing instead of throwing', () => {
		render({ fields: IDENTITY_METAS.filter((f) => f.key !== 'crc64service_enabled') });
		expect(screen.queryByRole('checkbox', { name: 'ARM community database (CRC64)' })).not.toBeInTheDocument();
		expect(screen.getByRole('checkbox', { name: 'TheDiscDB disc map' })).toBeInTheDocument();
	});
});
