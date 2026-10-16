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
const preview = () => screen.getByRole('group', { name: 'Identity preview' });
const previewRowLabels = () =>
	within(preview())
		.getAllByTestId(/^identity-preview-(disc|movie|tv|music)$/)
		.map((r) => r.querySelector('.identity-preview-label')?.textContent?.trim());
const pillText = (key: string) =>
	within(screen.getByTestId(`identity-preview-${key}`))
		.queryAllByTestId('identity-preview-pill')
		.map((p) => p.textContent?.replace(/\s+/g, ' ').trim());

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

	it('the Preview block has its caption, the control, then the panel', () => {
		render();
		const caption = screen.getByText('Preview', { selector: '.identity-card-caption' });
		const group = screen.getByRole('radiogroup', { name: 'Disc kind' });
		expect(caption.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		expect(group.compareDocumentPosition(preview()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		expect(preview().compareDocumentPosition(step(1)) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
	});

	it('clicking CD leaves Disc and Music only; Blu-ray restores Movies and TV shows', async () => {
		render();
		expect(previewRowLabels()).toEqual(['Disc', 'Movies', 'TV shows']);
		await fireEvent.click(screen.getByRole('radio', { name: 'CD' }));
		expect(screen.getByRole('radio', { name: 'CD' })).toHaveAttribute('aria-checked', 'true');
		expect(previewRowLabels()).toEqual(['Disc', 'Music']);
		expect(pillText('music')).toEqual(['1 MusicBrainz']);
		await fireEvent.click(screen.getByRole('radio', { name: 'Blu-ray' }));
		expect(previewRowLabels()).toEqual(['Disc', 'Movies', 'TV shows']);
	});

	it('unticking OMDb in Step 3 drops its pill and leaves 1 TMDb', async () => {
		render();
		expect(pillText('movie')).toEqual(['1 TMDb', '2 OMDb']);
		const movies = within(step(3)).getByRole('list', { name: 'Movie sources' });
		await fireEvent.click(within(movies).getByRole('checkbox', { name: 'Use OMDb' }));
		expect(pillText('movie')).toEqual(['1 TMDb']);
		expect(pillText('tv')).toEqual(['1 TMDb', '2 TVmaze', '3 TVDB']);
	});

	it('step headings carry the number and the sentence-case title; Advanced has no badge', () => {
		render();
		const names = ['1 On the disc', '2 Disc database', '3 Online lookup', '4 Trust'];
		names.forEach((name, i) => {
			const h = within(step(i + 1)).getByRole('heading', { name });
			expect(h.querySelector('.identity-card-badge')).toHaveTextContent(String(i + 1));
		});
		const advanced = document.querySelector('.identity-card-step[data-step="advanced"]') as HTMLElement;
		expect(advanced.querySelector('.identity-card-badge')).toBeNull();
	});

	it('Step 1 lists the three disc rows with their chips and no controls', () => {
		render();
		const s1 = step(1);
		expect(within(s1).getByRole('heading', { name: '1 On the disc' })).toBeInTheDocument();
		const rows = within(s1).getAllByTestId(/^identity-row-/);
		expect(rows.map((r) => r.querySelector('.identity-card-row-name')?.textContent?.trim())).toEqual([
			'Disc title metadata',
			'Volume label',
			'Disc ID (track layout)'
		]);
		const chips = (r: HTMLElement) => Array.from(r.querySelectorAll('.chip')).map((c) => c.textContent?.trim());
		expect(chips(rows[0])).toEqual(['Blu-ray', 'UHD']);
		expect(chips(rows[1])).toEqual(['All discs']);
		expect(chips(rows[2])).toEqual(['CD']);
		expect(s1.querySelectorAll('input, select, button')).toHaveLength(0);
		expect(s1).toHaveTextContent(
			"ARM reads all of these. When they disagree, the disc's own metadata beats its label."
		);
	});

	it('Step 2 has the two disc database checkboxes with their chips and descriptions', () => {
		render();
		const s2 = step(2);
		expect(within(s2).getByRole('heading', { name: '2 Disc database' })).toBeInTheDocument();
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

	it('Step 3 shows the Movies and TV shows ranked lists with the tolerance under TV, and no Music list', () => {
		render();
		const s3 = step(3);
		expect(within(s3).getByRole('heading', { name: '3 Online lookup' })).toBeInTheDocument();
		expect(s3).toHaveTextContent('Tried top to bottom; the first confident match wins.');
		for (const name of ['Movie sources', 'Episode sources']) {
			expect(within(s3).getByRole('list', { name })).toBeInTheDocument();
		}
		expect(within(s3).queryByRole('list', { name: 'Music sources' })).toBeNull();
		expect(s3.querySelector('#setting-music_sources')).toBeNull();
		expect(within(s3).queryByText('CDDB')).toBeNull();
		expect(within(s3).getAllByText('Rank 1')).toHaveLength(2);
		const tv = s3.querySelector('#setting-episode_sources') as HTMLElement;
		expect(within(tv).getByRole('heading', { name: 'TV shows' })).toBeInTheDocument();
		expect(within(tv).getByRole('spinbutton', { name: 'Episode match tolerance (seconds)' })).toHaveValue(300);
		expect(s3).not.toHaveTextContent('No sources on');
	});

	it('an empty list shows No sources on under its heading', () => {
		render({ initial: { ...IDENTITY_DEFAULTS, movie_sources: [] } });
		const movies = step(3).querySelector('#setting-movie_sources') as HTMLElement;
		expect(movies).toHaveTextContent('No sources on');
	});

	it('Step 4 stacks the three Apply confident matches boxes with no caption, bound to the auto-apply fields', async () => {
		const { component } = render();
		const s4 = step(4);
		expect(within(s4).getByRole('heading', { name: '4 Trust' })).toBeInTheDocument();
		expect(s4.querySelector('#identity-trust-caption')).toBeNull();
		expect(within(s4).queryByText('Apply confident matches', { exact: true })).toBeNull();
		const boxes = within(s4).getAllByRole('checkbox');
		const labels = [
			'Apply confident matches · Movies',
			'Apply confident matches · TV shows',
			'Apply confident matches · Music'
		];
		expect(boxes.map((c) => c.getAttribute('aria-label'))).toEqual(labels);
		for (const l of labels) expect(within(s4).getByText(l)).toBeInTheDocument();
		expect(s4).toHaveTextContent(
			'When off, a match waits on the job page for you to confirm it and the disc is held with no countdown. Ripping › Review first still holds every disc.'
		);
		await fireEvent.click(within(s4).getByRole('checkbox', { name: 'Apply confident matches · Movies' }));
		expect((component as unknown as { getValues: () => Record<string, unknown> }).getValues().movie_auto_apply).toBe(
			false
		);
		expect(screen.getByTestId('identity-preview-movie')).toHaveTextContent('Waits for review');
		expect(screen.getByTestId('identity-preview-tv')).toHaveTextContent('Applies confident matches');
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
		const advanced = document.querySelector('.identity-card-step[data-step="advanced"]') as HTMLElement;
		expect(advanced).toHaveTextContent(
			"For collections where the disc's own text is usually wrong. Fix a single disc from its job page instead."
		);
		expect(advanced).not.toHaveTextContent('With the volume label ignored');
	});

	it('Advanced: each Ignore box has its sub-line', () => {
		render();
		expect(screen.getByRole('checkbox', { name: 'Ignore the disc title metadata' })).toHaveAccessibleDescription(
			"Blu-ray and UHD only. ARM won't use the title stored on the disc and identifies it from the volume label, TheDiscDB and online lookup instead."
		);
		expect(screen.getByRole('checkbox', { name: 'Ignore the volume label' })).toHaveAccessibleDescription(
			"ARM won't use the volume label and identifies the disc from its title metadata, TheDiscDB and online lookup instead. A DVD with no title metadata then gets no automatic title search."
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
		expect(screen.getByTestId('identity-preview-disc')).toHaveTextContent(
			'Volume label, then TheDiscDB and the ARM community database'
		);
	});

	it('skips a control whose meta is missing instead of throwing', () => {
		render({ fields: IDENTITY_METAS.filter((f) => f.key !== 'crc64service_enabled') });
		expect(screen.queryByRole('checkbox', { name: 'ARM community database (CRC64)' })).not.toBeInTheDocument();
		expect(screen.getByRole('checkbox', { name: 'TheDiscDB disc map' })).toBeInTheDocument();
	});
});
