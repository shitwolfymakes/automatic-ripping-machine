import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/test-utils';
import type { HandbrakeSchemaSlimView } from '$lib/types/api.gen';
import fixture from '$lib/handbrake/__tests__/fixtures/slim-schema.json';
import SettingsPanel from '../SettingsPanel.svelte';

const schema = fixture as unknown as HandbrakeSchemaSlimView;

function mount(tab: string, common: Record<string, unknown> = {}, filter = { text: '', changedOnly: false }) {
	return renderComponent(SettingsPanel, {
		props: {
			schema,
			settings: { common, encoders: {} },
			base: null,
			issues: [],
			readonly: false,
			encoder: 'x264',
			availability: [],
			cards: [],
			expanded: [],
			onsettings: vi.fn(),
			onexpand: vi.fn(),
			tab,
			filter
		}
	});
}
const group = (name: string) => screen.getByRole('group', { name });

describe('SettingsPanel group cards', () => {
	afterEach(() => cleanup());

	it('renders each visible group as a card headed by its name', () => {
		mount('dimensions');
		const size = group('Size');
		expect(size).toHaveClass('form-card');
		expect(within(size).getByRole('heading', { name: 'Size' })).toBeInTheDocument();
		expect(group('Cropping')).toHaveClass('form-card');
	});

	it('uses a plain div head so theme header rules cannot reach it, and no landmark', () => {
		mount('dimensions');
		const size = group('Size');
		expect(size.querySelector('header')).toBeNull();
		expect(size.querySelector('div.form-card-head')).not.toBeNull();
		expect(screen.queryByRole('region', { name: 'Size' })).toBeNull();
	});

	it('shows the changed count on a group with stored values and no chip on one without', () => {
		mount('dimensions', { PictureForceWidth: 1, PictureForceHeight: 2, PictureAutoCrop: true });
		expect(group('Size').querySelector('.changed-chip')).toHaveTextContent(/^2 changed$/);
		expect(group('Cropping').querySelector('.changed-chip')).toHaveTextContent(/^1 changed$/);
		expect(group('Padding').querySelector('.changed-chip')).toBeNull();
	});

	it('renders no card for a group with no visible field', () => {
		mount('dimensions', { PictureForceWidth: 1 }, { text: '', changedOnly: true });
		expect(group('Size')).toBeInTheDocument();
		expect(screen.queryByRole('group', { name: 'Cropping' })).toBeNull();
	});

	it('nests the audio track cards inside the Tracks group card', () => {
		mount('audio', { AudioList: [{}] });
		const track = within(group('Tracks')).getByRole('region', { name: 'Audio track 1' });
		expect(track).toHaveClass('form-card', 'form-card-nested');
	});
});
