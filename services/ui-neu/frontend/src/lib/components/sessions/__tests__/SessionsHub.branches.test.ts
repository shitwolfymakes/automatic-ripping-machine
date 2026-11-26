import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import SessionsHub from '../SessionsHub.svelte';

// Branch pins for SessionsHub, beside SessionsHub.svelte.test.ts. No branch
// is left open.

const j = (id: string, name: string, mt: string, tc: string | null, builtin = false) =>
	({
		id,
		name,
		media_type: mt,
		is_builtin: builtin,
		rip_preset_id: 'r1',
		transcode_preset_id: tc,
		output_path_template: 'x/{title}.{ext}',
		overrides_json: null,
		ripPreset: { id: 'r1', name: 'Rip', track_selection: 'main_feature', output_mode: 'tracks' },
		transcodePreset: tc ? { id: tc, name: 'TC', container: 'mkv', encoder: 'any_h265' } : undefined
	}) as any;
const props = (over = {}) => ({
	sessions: [
		j('s1', 'Alpha', 'movie', 't1'),
		j('s2', 'Beta', 'movie', null),
		j('s3', 'Gamma', 'tv', 't2', true),
		j('s4', 'Delta', 'tv', null, true)
	],
	typeCounts: { all: 4, movie: 2, tv: 2, music: 0, data: 0, iso: 0 },
	loading: false,
	onedit: vi.fn(),
	onclone: vi.fn(),
	ondelete: vi.fn(),
	onnew: vi.fn(),
	...over
});

const choose = (label: RegExp, value: string) =>
	fireEvent.change(screen.getByRole('combobox', { name: label }), { target: { value } });

const NAMES = ['Alpha', 'Beta', 'Gamma', 'Delta'];
const expectShown = (shown: string[]) => {
	for (const n of NAMES) {
		if (shown.includes(n)) expect(screen.getByText(n)).toBeInTheDocument();
		else expect(screen.queryByText(n)).not.toBeInTheDocument();
	}
};

afterEach(cleanup);

describe('SessionsHub filters', () => {
	it.each([
		['builtin', ['Gamma', 'Delta']],
		['custom', ['Alpha', 'Beta']],
		['all', NAMES]
	])('source choice %s shows the matching sessions', async (value, shown) => {
		renderComponent(SessionsHub, props());
		await choose(/filter by source/i, 'builtin');
		await choose(/filter by source/i, value);
		expectShown(shown);
	});

	it.each([
		['has', ['Alpha', 'Gamma']],
		['none', ['Beta', 'Delta']],
		['any', NAMES]
	])('transcode choice %s shows the matching sessions', async (value, shown) => {
		renderComponent(SessionsHub, props());
		await choose(/filter by transcode/i, 'has');
		await choose(/filter by transcode/i, value);
		expectShown(shown);
	});

	it('combines the source and transcode choices', async () => {
		renderComponent(SessionsHub, props());
		await choose(/filter by source/i, 'builtin');
		await choose(/filter by transcode/i, 'none');
		expectShown(['Delta']);
	});

	it('search ignores case and surrounding spaces', async () => {
		renderComponent(SessionsHub, props());
		await fireEvent.input(screen.getByPlaceholderText(/search sessions/i), { target: { value: '  gAmMa ' } });
		expectShown(['Gamma']);
	});

	it('a blank search shows every session', async () => {
		renderComponent(SessionsHub, props());
		await fireEvent.input(screen.getByPlaceholderText(/search sessions/i), { target: { value: '   ' } });
		expectShown(NAMES);
	});

	it('says no sessions match when the filters leave nothing', async () => {
		renderComponent(SessionsHub, props());
		await fireEvent.input(screen.getByPlaceholderText(/search sessions/i), { target: { value: 'zzz' } });
		expect(screen.getByText('No sessions match your filters.')).toBeInTheDocument();
		expectShown([]);
	});
});

describe('SessionsHub type chips', () => {
	it('shows the counts from typeCounts', () => {
		renderComponent(SessionsHub, props());
		expect(screen.getByRole('button', { name: /^All 4$/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Movie 2$/ })).toBeInTheDocument();
	});

	it('shows 0 for a type the typeCounts prop leaves out', () => {
		renderComponent(SessionsHub, props({ typeCounts: { all: 4, movie: 2 } }));
		for (const label of ['TV', 'Music', 'Data', 'ISO']) {
			expect(screen.getByRole('button', { name: new RegExp(`^${label} 0$`) })).toBeInTheDocument();
		}
	});

	it('a chip press filters the list and All brings every session back', async () => {
		renderComponent(SessionsHub, props());
		await fireEvent.click(screen.getByRole('button', { name: /^Movie/ }));
		expect(screen.getByRole('button', { name: /^Movie/ })).toHaveAttribute('aria-pressed', 'true');
		expectShown(['Alpha', 'Beta']);
		await fireEvent.click(screen.getByRole('button', { name: /^All/ }));
		expectShown(NAMES);
	});
});
