import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import SessionsSection from '../SessionsSection.svelte';
import { fetchSessions, deleteSession, cloneSession } from '$lib/api/sessions';
import { fetchRipPresets } from '$lib/api/ripPresets';
import { fetchTranscodePresets } from '$lib/api/transcodePresets';
import type { RipPresetView, SessionView, TranscodePresetView } from '$lib/types/api.gen';

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(),
	deleteSession: vi.fn(),
	cloneSession: vi.fn(),
	createSession: vi.fn(),
	updateSession: vi.fn(),
	previewTemplate: vi.fn()
}));
vi.mock('$lib/api/ripPresets', () => ({ fetchRipPresets: vi.fn() }));
vi.mock('$lib/api/transcodePresets', () => ({ fetchTranscodePresets: vi.fn() }));

const fetchMock = vi.mocked(fetchSessions);
const deleteMock = vi.mocked(deleteSession);
const cloneMock = vi.mocked(cloneSession);
const ripMock = vi.mocked(fetchRipPresets);
const tcMock = vi.mocked(fetchTranscodePresets);

function makeSession(overrides: Partial<SessionView> = {}): SessionView {
	return {
		id: 'ses_1',
		name: 'My session',
		media_type: 'movie',
		is_builtin: false,
		rip_preset_id: 'rp_movie',
		transcode_preset_id: 'tp_movie',
		output_path_template: '/media/{title}',
		overrides_json: null,
		created_by_user_id: 'u1',
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...overrides
	} as SessionView;
}

beforeEach(() => {
	fetchMock.mockReset();
	deleteMock.mockReset().mockResolvedValue(undefined);
	cloneMock.mockReset();
	ripMock.mockReset().mockResolvedValue([
		{ id: 'rp_movie', name: 'Movie rip', media_type: 'movie', is_builtin: false } as RipPresetView
	]);
	tcMock.mockReset().mockResolvedValue([
		{ id: 'tp_movie', name: 'Movie tc', media_type: 'movie', is_builtin: false } as TranscodePresetView
	]);
});
afterEach(() => cleanup());

describe('SessionsSection', () => {
	it('renders the list with resolved rip + transcode preset names', async () => {
		fetchMock.mockResolvedValue([makeSession({ id: 's1', name: 'Movies' })]);
		renderComponent(SessionsSection);
		await waitFor(() => expect(screen.getByText('Movies')).toBeInTheDocument());
		expect(screen.getByText('Movie rip')).toBeInTheDocument();
		expect(screen.getByText('Movie tc')).toBeInTheDocument();
	});

	it('shows "— none —" when the session has no transcode preset', async () => {
		fetchMock.mockResolvedValue([makeSession({ id: 's2', name: 'No TC', transcode_preset_id: null })]);
		renderComponent(SessionsSection);
		await waitFor(() => expect(screen.getByText('No TC')).toBeInTheDocument());
		expect(screen.getByText('- none -')).toBeInTheDocument();
	});

	it('falls back to the raw id when a preset is not in the map', async () => {
		fetchMock.mockResolvedValue([makeSession({ id: 's3', name: 'Orphan', rip_preset_id: 'rp_GONE' })]);
		renderComponent(SessionsSection);
		await waitFor(() => expect(screen.getByText('Orphan')).toBeInTheDocument());
		expect(screen.getByText('rp_GONE')).toBeInTheDocument();
	});

	it('Clone is available on a built-in (Delete is not)', async () => {
		fetchMock.mockResolvedValue([makeSession({ id: 'b', name: 'Stock', is_builtin: true })]);
		renderComponent(SessionsSection);
		await waitFor(() => expect(screen.getByText('Stock')).toBeInTheDocument());
		expect(screen.getByTestId('session-clone')).toBeInTheDocument();
		expect(screen.queryByTestId('session-delete')).not.toBeInTheDocument();
		expect(screen.getByTestId('session-builtin-badge')).toBeInTheDocument();
	});

	it('clone box prefills "<name> (copy)" and calls cloneSession', async () => {
		fetchMock.mockResolvedValue([makeSession({ id: 's4', name: 'Movies' })]);
		cloneMock.mockResolvedValue(makeSession({ id: 'clone_1', name: 'Movies (copy)' }));
		renderComponent(SessionsSection);
		await waitFor(() => expect(screen.getByText('Movies')).toBeInTheDocument());

		await fireEvent.click(screen.getByTestId('session-clone'));
		const cloneName = screen.getByTestId('session-clone-name') as HTMLInputElement;
		expect(cloneName.value).toBe('Movies (copy)');
		await fireEvent.click(screen.getByTestId('session-clone-submit'));

		await waitFor(() => expect(cloneMock).toHaveBeenCalledWith('s4', { name: 'Movies (copy)' }));
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it('deletes after confirming the dialog', async () => {
		fetchMock.mockResolvedValue([makeSession({ id: 'del_me', name: 'Delete me' })]);
		renderComponent(SessionsSection);
		await waitFor(() => expect(screen.getByText('Delete me')).toBeInTheDocument());

		await fireEvent.click(screen.getByTestId('session-delete'));
		await waitFor(() => expect(screen.getByText('Delete session')).toBeInTheDocument());
		const deleteButtons = screen.getAllByText('Delete');
		await fireEvent.click(deleteButtons[deleteButtons.length - 1]);

		await waitFor(() => expect(deleteMock).toHaveBeenCalledWith('del_me'));
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it('Edit expands an inline form row beneath the edited row (not a below-table panel)', async () => {
		fetchMock.mockResolvedValue([makeSession({ id: 'ed', name: 'Editable' })]);
		renderComponent(SessionsSection);
		await waitFor(() => expect(screen.getByText('Editable')).toBeInTheDocument());

		expect(screen.queryByTestId('session-edit-row')).not.toBeInTheDocument();

		await fireEvent.click(screen.getByTestId('session-edit'));

		const editRow = await screen.findByTestId('session-edit-row');
		expect(editRow).toBeInTheDocument();
		// The inline form lives inside the expanded row.
		expect(editRow.querySelector('[data-testid="session-form"]')).not.toBeNull();
		// Expanded row is the immediate sibling after the edited session row.
		const sessionRow = screen.getByTestId('session-row');
		expect(sessionRow.nextElementSibling).toBe(editRow);
	});

	it('surfaces a delete error inline', async () => {
		fetchMock.mockResolvedValue([makeSession({ id: 'ref', name: 'Referenced' })]);
		deleteMock.mockRejectedValue(new Error('referenced by a job'));
		renderComponent(SessionsSection);
		await waitFor(() => expect(screen.getByText('Referenced')).toBeInTheDocument());
		await fireEvent.click(screen.getByTestId('session-delete'));
		await waitFor(() => expect(screen.getByText('Delete session')).toBeInTheDocument());
		const deleteButtons = screen.getAllByText('Delete');
		await fireEvent.click(deleteButtons[deleteButtons.length - 1]);
		await waitFor(() => expect(screen.getByTestId('sessions-error')).toHaveTextContent('referenced by a job'));
	});
});
