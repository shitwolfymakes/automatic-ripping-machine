import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, waitFor, cleanup } from '$lib/test-utils';
import type { JobStatus } from '$lib/types/api.gen';
import { resolveJob } from '$lib/api/jobs';
import JobInfoForm from '../JobInfoForm.svelte';
import { actionsFor } from '../../__fixtures__/job';

// Branch pins for JobInfoForm, beside JobInfoForm.test.ts. Every branch is
// reachable from the rendered component.

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

vi.mock('$lib/api/jobs', () => ({
	resolveJob: vi.fn()
}));

const mockResolve = vi.mocked(resolveJob);

function job(overrides: Record<string, unknown> = {}) {
	return {
		id: 'job_1',
		drive_id: 'drv_1',
		disc_type: 'dvd',
		status: 'awaiting_user_id',
		actions: actionsFor((overrides.status as JobStatus | undefined) ?? 'awaiting_user_id'),
		title: 'Star Knight',
		year: 1985,
		season: 2,
		disc_number: 3,
		disc_total: 4,
		metadata_json: {},
		resumed_from_crash: false,
		...overrides
	} as any;
}

const LABELS = ['Title', 'Year', 'Season', 'Disc number', 'Disc total'] as const;

function value(label: string): string {
	return (screen.getByLabelText(label) as HTMLInputElement).value;
}

function values(): string[] {
	return LABELS.map(value);
}

async function typeInto(label: string, v: string) {
	await fireEvent.input(screen.getByLabelText(label), { target: { value: v } });
}

async function clickSave() {
	await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
}

beforeEach(() => {
	mockResolve.mockReset();
	mockResolve.mockResolvedValue({ job: job(), fan_out: [] } as any);
});

afterEach(() => {
	cleanup();
});

describe('JobInfoForm seeding', () => {
	it('seeds every field from the job as text and digits', () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		expect(values()).toEqual(['Star Knight', '1985', '2', '3', '4']);
	});

	it('seeds every null field as an empty string', () => {
		renderComponent(JobInfoForm, {
			props: { job: job({ title: null, year: null, season: null, disc_number: null, disc_total: null }) }
		});
		expect(values()).toEqual(['', '', '', '', '']);
	});

	it('seeds a field the job leaves undefined as an empty string', () => {
		renderComponent(JobInfoForm, {
			props: { job: job({ season: undefined, disc_number: undefined, disc_total: undefined }) }
		});
		expect(values()).toEqual(['Star Knight', '1985', '', '', '']);
	});

	const CHANGED = {
		title: 'Polled Title',
		year: 1999,
		season: 5,
		disc_number: 6,
		disc_total: 7
	};
	const FIELDS: [string, number][] = [
		['Title', 0],
		['Year', 1],
		['Season', 2],
		['Disc number', 3],
		['Disc total', 4]
	];

	it.each(FIELDS)('a rerender keeps a touched %s and re-seeds the other four', async (label, idx) => {
		const { rerender } = renderComponent(JobInfoForm, { props: { job: job() } });
		await typeInto(label, label === 'Title' ? 'My Edit' : '9');
		await rerender({ job: job(CHANGED) });
		const expected = ['Polled Title', '1999', '5', '6', '7'];
		expected[idx] = label === 'Title' ? 'My Edit' : '9';
		expect(values()).toEqual(expected);
	});

	it('a rerender re-seeds a field that is cleared on the new job', async () => {
		const { rerender } = renderComponent(JobInfoForm, { props: { job: job() } });
		await rerender({ job: job({ title: null, year: null, season: null, disc_number: null, disc_total: null }) });
		expect(values()).toEqual(['', '', '', '', '']);
	});

	it('Reset clears the marks and feedback, hides the save bar and re-seeds every field', async () => {
		mockResolve.mockRejectedValueOnce(new Error('boom'));
		renderComponent(JobInfoForm, { props: { job: job() } });
		await typeInto('Title', 'Edited');
		await typeInto('Year', '2001');
		await typeInto('Season', '8');
		await typeInto('Disc number', '9');
		await typeInto('Disc total', '10');
		await clickSave();
		await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument());
		await fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
		expect(values()).toEqual(['Star Knight', '1985', '2', '3', '4']);
		expect(screen.queryByText('boom')).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Reset' })).not.toBeInTheDocument();
	});
});

describe('JobInfoForm request body', () => {
	it('sends the trimmed title and every number as a number', async () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		await typeInto('Title', '  New Title  ');
		await typeInto('Year', '2001');
		await typeInto('Disc number', '5');
		await typeInto('Disc total', '6');
		await clickSave();
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(mockResolve.mock.calls[0][0]).toBe('job_1');
		expect(mockResolve.mock.calls[0][1]).toStrictEqual({
			title: 'New Title',
			year: 2001,
			disc_number: 5,
			disc_total: 6
		});
	});

	it('sends year, disc number and disc total as null when cleared', async () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		await typeInto('Year', '');
		await typeInto('Disc number', '');
		await typeInto('Disc total', '');
		await clickSave();
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(mockResolve.mock.calls[0][1]).toStrictEqual({
			title: 'Star Knight',
			year: null,
			disc_number: null,
			disc_total: null
		});
	});

	it('sends the season as a number when it was touched', async () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		await typeInto('Season', '7');
		await clickSave();
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(mockResolve.mock.calls[0][1]).toStrictEqual({
			title: 'Star Knight',
			year: 1985,
			season: 7,
			disc_number: 3,
			disc_total: 4
		});
	});

	it('sends the season as null when it was cleared', async () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		await typeInto('Season', '');
		await clickSave();
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(mockResolve.mock.calls[0][1]).toStrictEqual({
			title: 'Star Knight',
			year: 1985,
			season: null,
			disc_number: 3,
			disc_total: 4
		});
	});

	it('sends no season key when Season was untouched', async () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		await typeInto('Year', '1990');
		await clickSave();
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		const body = mockResolve.mock.calls[0][1];
		expect(Object.keys(body)).toEqual(['title', 'year', 'disc_number', 'disc_total']);
	});
});

describe('JobInfoForm saved diff', () => {
	async function saveAndGetDiff(before: Record<string, unknown>, resp: unknown) {
		mockResolve.mockResolvedValue(resp as any);
		const onsaved = vi.fn();
		renderComponent(JobInfoForm, { props: { job: job(before), onsaved } });
		await typeInto('Year', '1990');
		await clickSave();
		await waitFor(() => expect(onsaved).toHaveBeenCalledTimes(1));
		return onsaved.mock.calls[0][0];
	}

	it('reports a season change only', async () => {
		const diff = await saveAndGetDiff({}, { job: job({ season: 9 }), fan_out: [] });
		expect(diff).toStrictEqual({ season: true, disc: false });
	});

	it('reports a disc change only', async () => {
		const diff = await saveAndGetDiff({}, { job: job({ disc_number: 9 }), fan_out: [] });
		expect(diff).toStrictEqual({ season: false, disc: true });
	});

	it('reports both changes', async () => {
		const diff = await saveAndGetDiff({}, { job: job({ season: 9, disc_number: 8 }), fan_out: [] });
		expect(diff).toStrictEqual({ season: true, disc: true });
	});

	it('reports neither change', async () => {
		const diff = await saveAndGetDiff({}, { job: job({ disc_total: 9 }), fan_out: [] });
		expect(diff).toStrictEqual({ season: false, disc: false });
	});

	it('reports neither change for a response with no job', async () => {
		const diff = await saveAndGetDiff({}, { fan_out: [] });
		expect(diff).toStrictEqual({ season: false, disc: false });
	});

	it('reports neither change for an empty response', async () => {
		const diff = await saveAndGetDiff({}, undefined);
		expect(diff).toStrictEqual({ season: false, disc: false });
	});

	it('reports no season change when a cleared season comes back the same', async () => {
		mockResolve.mockResolvedValue({ job: job({ season: 2 }), fan_out: [] } as any);
		const onsaved = vi.fn();
		renderComponent(JobInfoForm, { props: { job: job({ season: 2 }), onsaved } });
		await typeInto('Season', '');
		await clickSave();
		await waitFor(() => expect(onsaved).toHaveBeenCalledTimes(1));
		expect(mockResolve.mock.calls[0][1]).toHaveProperty('season', null);
		expect(onsaved).toHaveBeenCalledWith({ season: false, disc: false });
	});

	it('compares an undefined season and disc number as null', async () => {
		const before = { season: undefined, disc_number: undefined };
		const diff = await saveAndGetDiff(before, {
			job: job({ season: null, disc_number: null }),
			fan_out: []
		});
		expect(diff).toStrictEqual({ season: false, disc: false });
	});

	it('compares a response with an undefined season and disc number as null', async () => {
		const diff = await saveAndGetDiff(
			{ season: null, disc_number: null },
			{ job: job({ season: undefined, disc_number: undefined }), fan_out: [] }
		);
		expect(diff).toStrictEqual({ season: false, disc: false });
	});

	it('reports a change from an undefined season and disc number to a value', async () => {
		const diff = await saveAndGetDiff(
			{ season: undefined, disc_number: undefined },
			{ job: job({ season: 1, disc_number: 1 }), fan_out: [] }
		);
		expect(diff).toStrictEqual({ season: true, disc: true });
	});
});

describe('JobInfoForm after a save', () => {
	it('shows Saved, clears the marks, then calls onrefresh before onsaved', async () => {
		const calls: string[] = [];
		const onrefresh = vi.fn(() => calls.push('refresh'));
		const onsaved = vi.fn(() => calls.push('saved'));
		renderComponent(JobInfoForm, { props: { job: job(), onrefresh, onsaved } });
		await typeInto('Year', '1990');
		await clickSave();
		const saved = await screen.findByText('Saved');
		expect(saved).toHaveAttribute('data-tone', 'success');
		expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
		expect(calls).toEqual(['refresh', 'saved']);
		expect(onsaved).toHaveBeenCalledWith({ season: false, disc: false });
	});

	it.each([
		['neither callback', {}],
		['only onrefresh', { onrefresh: vi.fn() }],
		['only onsaved', { onsaved: vi.fn() }]
	])('saves cleanly with %s passed', async (_name, callbacks) => {
		renderComponent(JobInfoForm, { props: { job: job(), ...callbacks } });
		await typeInto('Year', '1990');
		await clickSave();
		expect(await screen.findByText('Saved')).toHaveAttribute('data-tone', 'success');
		expect(screen.queryByText('Save failed')).not.toBeInTheDocument();
	});

	it("shows the Error's message, keeps the save bar and calls neither callback", async () => {
		mockResolve.mockRejectedValueOnce(new Error('boom'));
		const onrefresh = vi.fn();
		const onsaved = vi.fn();
		renderComponent(JobInfoForm, { props: { job: job(), onrefresh, onsaved } });
		await typeInto('Year', '1990');
		await clickSave();
		expect(await screen.findByText('boom')).toHaveAttribute('data-tone', 'error');
		expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
		expect(onrefresh).not.toHaveBeenCalled();
		expect(onsaved).not.toHaveBeenCalled();
	});

	it('shows "Save failed" for a rejection that is not an Error', async () => {
		mockResolve.mockRejectedValueOnce('nope');
		const onrefresh = vi.fn();
		const onsaved = vi.fn();
		renderComponent(JobInfoForm, { props: { job: job(), onrefresh, onsaved } });
		await typeInto('Year', '1990');
		await clickSave();
		expect(await screen.findByText('Save failed')).toHaveAttribute('data-tone', 'error');
		expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
		expect(onrefresh).not.toHaveBeenCalled();
		expect(onsaved).not.toHaveBeenCalled();
	});

	it('shows Saving... with Save and Reset disabled while the request is pending', async () => {
		let finish: (v: unknown) => void = () => {};
		mockResolve.mockReturnValueOnce(new Promise((resolve) => (finish = resolve)) as any);
		renderComponent(JobInfoForm, { props: { job: job() } });
		await typeInto('Year', '1990');
		await clickSave();
		expect(await screen.findByRole('button', { name: 'Saving...' })).toBeDisabled();
		expect(screen.getByRole('button', { name: 'Reset' })).toBeDisabled();
		finish({ job: job(), fan_out: [] });
		expect(await screen.findByText('Saved')).toBeInTheDocument();
	});

	it('blank title keeps Save disabled', async () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		await typeInto('Title', '   ');
		expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
		expect(mockResolve).not.toHaveBeenCalled();
	});
});

describe('JobInfoForm focus', () => {
	it('puts the cursor in Season when focusField is season', async () => {
		renderComponent(JobInfoForm, { props: { job: job(), focusField: 'season' } });
		await waitFor(() => expect(screen.getByLabelText('Season')).toHaveFocus());
	});

	it('focuses no field without focusField', async () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		await Promise.resolve();
		for (const label of LABELS) expect(screen.getByLabelText(label)).not.toHaveFocus();
	});
});
