import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, within, cleanup } from '$lib/test-utils';
import ApplySessionRecipe from '../ApplySessionRecipe.svelte';
import type { JobNamingPreviewResponse, RipPresetView, SessionView, TranscodePresetView } from '$lib/types/api.gen';

function session(over: Partial<SessionView> = {}): SessionView {
	return { id: 's1', rip_preset_id: 'rp1', transcode_preset_id: 'tp1', ...over } as SessionView;
}

const RIP = [{ id: 'rp1', name: 'Rip Everything' }] as RipPresetView[];
const TC = [{ id: 'tp1', name: 'HQ 1080p' }] as TranscodePresetView[];

function previewOf(paths: string[]): JobNamingPreviewResponse {
	return {
		items: paths.map((output_path, i) => ({ track_id: `t${i}`, output_path }))
	} as JobNamingPreviewResponse;
}

function renderRecipe(over: Record<string, unknown> = {}) {
	renderComponent(ApplySessionRecipe, {
		props: {
			session: session(),
			ripPresets: RIP,
			transcodePresets: TC,
			preview: null,
			loading: false,
			problem: null,
			...over
		}
	});
}

afterEach(() => {
	cleanup();
});

describe('ApplySessionRecipe', () => {
	it('shows the rip preset name', () => {
		renderRecipe();
		expect(screen.getByTestId('recipe-rip-preset').textContent?.trim()).toBe('Rip Everything');
	});

	it('shows the rip preset id when it is not in the list', () => {
		renderRecipe({ ripPresets: [] });
		expect(screen.getByTestId('recipe-rip-preset').textContent?.trim()).toBe('rp1');
	});

	it('shows the transcode preset name', () => {
		renderRecipe();
		expect(screen.getByTestId('recipe-transcode-preset').textContent?.trim()).toBe('HQ 1080p');
	});

	it('shows No transcode when the session has no transcode preset', () => {
		renderRecipe({ session: session({ transcode_preset_id: null }) });
		expect(screen.getByTestId('recipe-transcode-preset').textContent?.trim()).toBe('No transcode');
	});

	it('shows No transcode when the transcode preset is not in the list', () => {
		renderRecipe({ transcodePresets: [] });
		expect(screen.getByTestId('recipe-transcode-preset').textContent?.trim()).toBe('No transcode');
	});

	it('shows Resolving... while loading', () => {
		renderRecipe({ loading: true, preview: previewOf(['/out/a.mkv']) });
		const cell = screen.getByTestId('recipe-output-path');
		expect(cell.textContent?.trim()).toBe('Resolving...');
		expect(within(cell).queryAllByRole('listitem')).toHaveLength(0);
	});

	it('lists each output path as an item with its title', () => {
		renderRecipe({ preview: previewOf(['/out/a.mkv', '/out/b.mkv']) });
		const items = within(screen.getByTestId('recipe-output-path')).getAllByRole('listitem');
		expect(items.map((li) => li.textContent)).toEqual(['/out/a.mkv', '/out/b.mkv']);
		expect(items.map((li) => li.getAttribute('title'))).toEqual(['/out/a.mkv', '/out/b.mkv']);
		expect(screen.queryByText('No tracks to transcode with this session.')).toBeNull();
	});

	it('says there are no tracks to transcode for an empty preview', () => {
		renderRecipe({ preview: previewOf([]) });
		expect(screen.getByText('No tracks to transcode with this session.')).toBeTruthy();
	});

	it('leaves the output cell empty with no preview and not loading', () => {
		renderRecipe();
		expect(screen.getByTestId('recipe-output-path').textContent?.trim()).toBe('');
	});

	it('shows the problem notice with its text', () => {
		renderRecipe({ problem: 'Missing year' });
		expect(screen.getByTestId('recipe-output-problem').textContent?.trim()).toBe('Missing year');
	});

	it('shows no problem notice when problem is null', () => {
		renderRecipe();
		expect(screen.queryByTestId('recipe-output-problem')).toBeNull();
	});
});
