import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import type { MetadataReleaseDetail } from '$lib/types/api.gen';
import type { TrackPair } from '$lib/music/release';
import { MusicReleaseApply } from '$lib/stores/music-release-apply.svelte';
import { MusicReleaseFields } from '$lib/stores/music-release-fields.svelte';
import { createJob } from '../../../../__fixtures__/job';
import MusicReleaseDetail from '../MusicReleaseDetail.svelte';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper, not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

const setRole = async (role: string | null) => {
	const auth = (await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void };
	auth.__setRole(role);
};

const fullDetail = {
	provider_id: 'mb-1',
	title: 'Kind of Blue',
	artist: 'Miles Davis',
	year: 1959,
	poster_url: null,
	country: 'US',
	format: 'CD',
	status: 'Official',
	disc_count: 2,
	catalog_number: 'CL 1355',
	barcode: '074646479324',
	tracks: []
} as unknown as MetadataReleaseDetail;

const bareDetail = {
	provider_id: 'mb-2',
	title: 'Bare',
	artist: null,
	year: null,
	poster_url: null,
	disc_count: 1,
	tracks: []
} as unknown as MetadataReleaseDetail;

const pair = {
	disc: { index: 0, expected_duration_seconds: 101 },
	mb: { title: 'So What', length_ms: 100000 },
	match: 'match'
} as unknown as TrackPair;

function renderDetail(
	overrides: {
		detail?: MetadataReleaseDetail;
		fields?: MusicReleaseFields;
		release?: MusicReleaseApply;
		onback?: () => void;
		onapply?: () => void;
	} = {}
) {
	const fields = overrides.fields ?? new MusicReleaseFields(createJob());
	if (!overrides.fields) fields.album = 'Kind of Blue';
	const release = overrides.release ?? new MusicReleaseApply();
	const onback = overrides.onback ?? vi.fn();
	const onapply = overrides.onapply ?? vi.fn();
	const view = renderComponent(MusicReleaseDetail, {
		props: {
			detail: overrides.detail ?? fullDetail,
			discTracks: [],
			tracks: [],
			pairs: [pair],
			mbTotalMs: 0,
			discTotalSec: null,
			fields,
			release,
			onback,
			onapply
		}
	});
	return { ...view, fields, release, onback, onapply };
}

describe('MusicReleaseDetail', () => {
	afterEach(async () => {
		cleanup();
		await setRole('admin');
	});

	it('shows the header with every fact present', () => {
		const { container } = renderDetail();
		expect(screen.getByText('Kind of Blue', { selector: 'p' })).toBeInTheDocument();
		expect(screen.getByText('Miles Davis')).toBeInTheDocument();
		expect(screen.getByText('US')).toBeInTheDocument();
		expect(screen.getByText('CD')).toBeInTheDocument();
		expect(screen.getByText('Official')).toBeInTheDocument();
		expect(screen.getByText('2 discs')).toBeInTheDocument();
		expect(container.querySelector('.music-search-catalog')?.textContent).toMatch(/Cat# CL 1355\s+\| 074646479324/);
	});

	it('leaves out absent facts, a single disc, the catalog number and the barcode', () => {
		const { container } = renderDetail({ detail: bareDetail });
		expect(screen.getByText('Bare', { selector: 'p' })).toBeInTheDocument();
		expect(container.querySelector('.music-search-detail-meta p:nth-child(2)')?.textContent).toBe('');
		expect(container.querySelector('.music-search-detail-meta p.flex')?.children).toHaveLength(0);
		expect(screen.queryByText(/discs/)).toBeNull();
		expect(container.querySelector('.music-search-catalog')?.textContent?.trim()).toBe('');
	});

	it('shows no disc count when it is missing', () => {
		renderDetail({ detail: { ...bareDetail, disc_count: null } as unknown as MetadataReleaseDetail });
		expect(screen.queryByText(/discs/)).toBeNull();
	});

	it('calls onback from Back to results', async () => {
		const { onback } = renderDetail();
		await fireEvent.click(screen.getByText('Back to results'));
		expect(onback).toHaveBeenCalledOnce();
	});

	it('shows the fields values and writes edits to the instance', async () => {
		const fields = new MusicReleaseFields(createJob());
		fields.album = 'Kind of Blue';
		fields.artist = 'Miles';
		fields.year = '1959';
		fields.discNumber = '1';
		fields.discTotal = '2';
		const { container } = renderDetail({ fields });
		const inputs = [...container.querySelectorAll('input')] as HTMLInputElement[];
		expect(inputs.map((i) => i.value)).toEqual(['Kind of Blue', 'Miles', '1959', '1', '2']);
		await fireEvent.input(inputs[0], { target: { value: 'New album' } });
		await fireEvent.input(inputs[1], { target: { value: 'New artist' } });
		await fireEvent.input(inputs[2], { target: { value: '2000' } });
		await fireEvent.input(inputs[3], { target: { value: '3' } });
		await fireEvent.input(inputs[4], { target: { value: '4' } });
		expect([fields.album, fields.artist, fields.year, fields.discNumber, fields.discTotal]).toEqual([
			'New album',
			'New artist',
			'2000',
			'3',
			'4'
		]);
	});

	it('calls onapply from Apply', async () => {
		const { onapply } = renderDetail();
		await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
		expect(onapply).toHaveBeenCalledOnce();
	});

	it('disables Apply while the album is blank', () => {
		const fields = new MusicReleaseFields(createJob());
		fields.album = '   ';
		renderDetail({ fields });
		expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
	});

	it('disables Apply and says Applying... while applying', () => {
		const release = new MusicReleaseApply();
		release.applying = true;
		renderDetail({ release });
		expect(screen.getByRole('button', { name: 'Applying...' })).toBeDisabled();
	});

	it('hides Apply for a guest', async () => {
		await setRole('guest');
		renderDetail();
		expect(screen.queryByRole('button', { name: 'Apply' })).toBeNull();
	});

	it('shows no gates by default', () => {
		renderDetail();
		expect(screen.queryByText(/Total length differs/)).toBeNull();
		expect(screen.queryByText('Confirm track title mapping')).toBeNull();
	});

	it('closes the mismatch alert from Cancel', async () => {
		const release = new MusicReleaseApply();
		release.confirmMismatch = true;
		const { onapply } = renderDetail({ release });
		expect(screen.getByText(/Total length differs/)).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(release.confirmMismatch).toBe(false);
		expect(screen.queryByText(/Total length differs/)).toBeNull();
		expect(onapply).not.toHaveBeenCalled();
	});

	it('confirms the mismatch and applies from Apply anyway', async () => {
		const release = new MusicReleaseApply();
		release.confirmMismatch = true;
		const { onapply } = renderDetail({ release });
		await fireEvent.click(screen.getByRole('button', { name: 'Apply anyway' }));
		expect(release.confirmMismatch).toBe(false);
		expect(onapply).toHaveBeenCalledOnce();
	});

	it('closes the mapping preview from Cancel', async () => {
		const release = new MusicReleaseApply();
		release.mappingPreview = true;
		const { onapply } = renderDetail({ release });
		expect(screen.getByText('Confirm track title mapping')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(release.mappingPreview).toBe(false);
		expect(onapply).not.toHaveBeenCalled();
	});

	it('confirms the mapping and applies from Apply titles', async () => {
		const release = new MusicReleaseApply();
		release.mappingPreview = true;
		const { onapply } = renderDetail({ release });
		await fireEvent.click(screen.getByRole('button', { name: 'Apply titles' }));
		expect(release.mappingPreview).toBe(false);
		expect(onapply).toHaveBeenCalledOnce();
	});

	it.each(['success', 'error'] as const)('shows the %s feedback line', (type) => {
		const release = new MusicReleaseApply();
		release.feedback = { type, message: `Message ${type}` };
		renderDetail({ release });
		expect(screen.getByText(`Message ${type}`)).toHaveAttribute('data-tone', type);
	});

	it('shows no feedback line when there is none', () => {
		const { container } = renderDetail();
		expect(container.querySelector('.music-search-feedback')).toBeNull();
	});
});
