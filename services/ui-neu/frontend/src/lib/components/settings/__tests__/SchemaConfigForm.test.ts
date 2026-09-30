import { describe, it, expect, vi, afterEach } from 'vitest';
import { createRawSnippet } from 'svelte';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/test-utils';
import SchemaConfigForm from '../SchemaConfigForm.svelte';
import { ApiError } from '$lib/api/client';
import { sectionFields } from '$lib/utils/settings-sections';
import type { SettingsGroup, KeyCheckResponse, ConfigFieldMeta } from '$lib/types/api.gen';

const saveArmConfig = vi.fn((_config: Record<string, unknown>) => Promise.resolve({ success: true }));
const checkApiKey = vi.fn((_name: string, _value?: string): Promise<KeyCheckResponse> =>
	Promise.resolve({ name: 'tmdb', status: 'ok', detail: null, checked_at: null })
);
vi.mock('$lib/api/settings', () => ({
	saveArmConfig: (config: Record<string, unknown>) => saveArmConfig(config),
	checkApiKey: (name: string, value?: string) => checkApiKey(name, value)
}));

// sectionFields itself is exercised end to end in settings-sections.test.ts;
// here it's a spy over the real implementation so most tests see the real
// Metadata sections while the layout-hints test below can swap in a fixed
// shape without depending on the production section map.
vi.mock('$lib/utils/settings-sections', async () => {
	const actual = await vi.importActual<typeof import('$lib/utils/settings-sections')>('$lib/utils/settings-sections');
	return { ...actual, sectionFields: vi.fn(actual.sectionFields) };
});

const GROUP: SettingsGroup = {
	name: 'Metadata',
	fields: [
		{
			key: 'metadata_provider',
			group: 'Metadata',
			tier: 'operator',
			label: 'Provider',
			help: '',
			type: 'enum',
			editable: true,
			enum_values: ['tmdb', 'omdb']
		},
		{
			key: 'tmdb_api_key',
			group: 'Metadata',
			tier: 'secret',
			label: 'TMDb key',
			help: '',
			type: 'string',
			editable: true,
			enum_values: null
		},
		{
			key: 'makemkv_key',
			group: 'Metadata',
			tier: 'secret',
			label: 'MakeMKV key',
			help: '',
			type: 'string',
			editable: true,
			enum_values: null
		}
	]
};
const CONFIG = { metadata_provider: 'tmdb', tmdb_api_key: '<hidden>', makemkv_key: '<hidden>' };

afterEach(() => {
	cleanup();
	saveArmConfig.mockClear();
	checkApiKey.mockClear();
	vi.mocked(sectionFields).mockClear();
});

describe('SchemaConfigForm', () => {
	it('renders the beforeSave snippet above the Save button', () => {
		const beforeSave = createRawSnippet(() => ({ render: () => '<div data-testid="before-save">extra</div>' }));
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG, beforeSave } });
		const extra = screen.getByTestId('before-save');
		const save = screen.getByRole('button', { name: 'Save' });
		expect(extra.compareDocumentPosition(save) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
	});

	it('renders a control per editable field, seeded from config', async () => {
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		expect((screen.getByRole('combobox', { name: /provider/i }) as HTMLSelectElement).value).toBe('tmdb');
		expect(screen.getByLabelText(/tmdb key/i)).toBeInTheDocument();
	});

	it('saves only changed fields, omitting an untouched <hidden> secret', async () => {
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.change(screen.getByRole('combobox', { name: /provider/i }), { target: { value: 'omdb' } });
		await fireEvent.click(screen.getByRole('button', { name: /save/i }));
		await waitFor(() => expect(saveArmConfig).toHaveBeenCalled());
		const payload = saveArmConfig.mock.calls[0][0];
		expect(payload.metadata_provider).toBe('omdb');
		expect('tmdb_api_key' in payload).toBe(false);
	});

	it('includes a secret in the payload when the user types a new value', async () => {
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.input(screen.getByLabelText(/tmdb key/i), { target: { value: 'new-key' } });
		await fireEvent.click(screen.getByRole('button', { name: /save/i }));
		await waitFor(() => expect(saveArmConfig).toHaveBeenCalled());
		expect(saveArmConfig.mock.calls[0][0].tmdb_api_key).toBe('new-key');
	});
});

describe('SchemaConfigForm key-check button', () => {
	function tmdbCheckButton() {
		// testid div -> .flex-1 wrapper -> the "flex items-end gap-2" row that
		// also holds the Check button as a sibling.
		return screen.getByTestId('setting-tmdb_api_key').parentElement!.parentElement!.querySelector('button')!;
	}

	it('calls checkApiKey with the unsaved value when the user typed a new key', async () => {
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.input(screen.getByLabelText(/tmdb key/i), { target: { value: 'unsaved-key' } });
		await fireEvent.click(tmdbCheckButton());
		await waitFor(() => expect(checkApiKey).toHaveBeenCalledWith('tmdb', 'unsaved-key'));
	});

	it('calls checkApiKey with no value for an untouched <hidden> secret', async () => {
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.click(tmdbCheckButton());
		await waitFor(() => expect(checkApiKey).toHaveBeenCalledWith('tmdb', undefined));
	});

	it('shows "Checking..." disabled while the probe runs, then renders the ok result', async () => {
		let resolve!: (v: KeyCheckResponse) => void;
		checkApiKey.mockImplementation(
			(name: string) =>
				new Promise<KeyCheckResponse>((r) => {
					// makemkv's onMount auto-run resolves immediately so it doesn't
					// block the test; only the tmdb click's promise stays pending.
					if (name === 'makemkv') r({ name, status: 'unknown', detail: 'not checked yet', checked_at: null });
					else resolve = r;
				})
		);
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.click(tmdbCheckButton());
		expect(screen.getByRole('button', { name: /checking/i })).toBeDisabled();
		resolve({ name: 'tmdb', status: 'ok', detail: null, checked_at: '2026-09-05T00:00:00Z' });
		await waitFor(() => expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent(/valid/i));
	});

	it('renders the invalid result with its detail', async () => {
		checkApiKey.mockImplementation((name: string) =>
			Promise.resolve(
				name === 'tmdb'
					? { name, status: 'invalid', detail: 'TMDb rejected the key', checked_at: null }
					: { name, status: 'unknown', detail: 'not checked yet', checked_at: null }
			)
		);
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.click(tmdbCheckButton());
		await waitFor(() =>
			expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent('TMDb rejected the key')
		);
	});

	it('renders the missing result', async () => {
		checkApiKey.mockImplementation((name: string) =>
			Promise.resolve(
				name === 'tmdb'
					? { name, status: 'missing', detail: 'no key set', checked_at: null }
					: { name, status: 'unknown', detail: 'not checked yet', checked_at: null }
			)
		);
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.click(tmdbCheckButton());
		await waitFor(() => expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent(/no key set/i));
	});

	it('renders the unknown result with its detail', async () => {
		checkApiKey.mockImplementation((name: string) =>
			Promise.resolve(
				name === 'tmdb'
					? {
							name,
							status: 'unknown',
							detail: 'save the key; the ripper verifies it before the next rip',
							checked_at: null
						}
					: { name, status: 'unknown', detail: 'not checked yet', checked_at: null }
			)
		);
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.click(tmdbCheckButton());
		await waitFor(() =>
			expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent(
				'save the key; the ripper verifies it before the next rip'
			)
		);
	});

	it('renders the error result with its detail', async () => {
		checkApiKey.mockImplementation((name: string) =>
			Promise.resolve(
				name === 'tmdb'
					? { name, status: 'error', detail: 'transport error: boom', checked_at: null }
					: { name, status: 'unknown', detail: 'not checked yet', checked_at: null }
			)
		);
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.click(tmdbCheckButton());
		await waitFor(() =>
			expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent('transport error: boom')
		);
	});

	it('shows the checked-at time on an ok result', async () => {
		checkApiKey.mockImplementation((name: string) =>
			Promise.resolve(
				name === 'tmdb'
					? { name, status: 'ok', detail: null, checked_at: '2026-09-05T00:00:00Z' }
					: { name, status: 'unknown', detail: 'not checked yet', checked_at: null }
			)
		);
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.click(tmdbCheckButton());
		await waitFor(() => expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent(/checked/i));
	});

	it('does not run any check on mount', async () => {
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await new Promise((r) => setTimeout(r, 20));
		expect(checkApiKey).not.toHaveBeenCalled();
		expect(screen.getByTestId('key-check-makemkv_key')).toHaveTextContent('');
	});

	it('shows the detail beside Valid when the backend sends one', async () => {
		checkApiKey.mockResolvedValue({
			name: 'makemkv',
			status: 'ok',
			detail: 'using the monthly beta key',
			checked_at: null
		});
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.click(screen.getAllByRole('button', { name: /check api key/i })[1]);
		await waitFor(() =>
			expect(screen.getByTestId('key-check-makemkv_key')).toHaveTextContent('Valid, using the monthly beta key')
		);
	});
});

describe('SchemaConfigForm save feedback', () => {
	it('shows the server message in an alert when Save is rejected', async () => {
		const detail = 'episode_match_tolerance_seconds must be 1 to 1800';
		saveArmConfig.mockRejectedValueOnce(new ApiError(400, detail, { detail }));
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't save settings.");
		expect(screen.getByRole('alert')).toHaveTextContent('must be 1 to 1800');
	});

	it('shows a network-failure message when the request never reaches the server', async () => {
		saveArmConfig.mockRejectedValueOnce(new TypeError('Failed to fetch'));
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		const alert = await screen.findByRole('alert');
		expect(alert).toHaveTextContent("Couldn't save settings.");
		expect(alert).toHaveTextContent("The server didn't respond. Your changes are still here, so try Save again.");
	});

	it('shows a check-circle glyph beside a successful save', async () => {
		renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(screen.getByText('Saved')).toBeInTheDocument());
		expect(screen.queryByRole('alert')).not.toBeInTheDocument();
	});
});

describe('SchemaConfigForm section layout hints', () => {
	const fieldA: ConfigFieldMeta = {
		key: 'a',
		group: 'Metadata',
		tier: 'operator',
		label: 'Field A',
		help: '',
		type: 'bool',
		editable: true,
		enum_values: null
	};
	const fieldB: ConfigFieldMeta = { ...fieldA, key: 'b', label: 'Field B' };
	const fieldC: ConfigFieldMeta = { ...fieldA, key: 'c', label: 'Field C' };
	const fieldD: ConfigFieldMeta = { ...fieldA, key: 'd', label: 'Field D' };
	const LAYOUT_GROUP: SettingsGroup = { name: 'Metadata', fields: [fieldA, fieldB, fieldC, fieldD] };
	const LAYOUT_CONFIG = { a: true, b: true, c: true, d: true };

	it('renders column and advanced groups without repeating keys', () => {
		vi.mocked(sectionFields).mockReturnValueOnce([
			{
				title: 'Test section',
				columns: [[fieldA, fieldB]],
				fields: [fieldC],
				advanced: [fieldD]
			}
		]);

		renderComponent(SchemaConfigForm, { props: { group: LAYOUT_GROUP, config: LAYOUT_CONFIG } });

		// Each key rendered exactly once.
		expect(screen.getAllByRole('checkbox')).toHaveLength(4);

		const columnsGrid = screen.getByTestId('settings-section-columns');
		expect(within(columnsGrid).getByLabelText('Field A')).toBeInTheDocument();
		expect(within(columnsGrid).getByLabelText('Field B')).toBeInTheDocument();
		expect(within(columnsGrid).queryByLabelText('Field C')).not.toBeInTheDocument();
		expect(within(columnsGrid).queryByLabelText('Field D')).not.toBeInTheDocument();

		const advancedLabel = screen.getByText('Advanced');
		const fieldDCheckbox = screen.getByLabelText('Field D');
		// Field D renders after the "Advanced" label, not before it.
		expect(advancedLabel.compareDocumentPosition(fieldDCheckbox) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		const fieldCCheckbox = screen.getByLabelText('Field C');
		expect(fieldCCheckbox.compareDocumentPosition(advancedLabel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
	});

	it('renders the summary slot as a no-op until a named component is wired up', () => {
		// The 'tv-episodes' name is recognised (typed on SettingsSection), but
		// this task only wires the slot - Task 6 supplies the component, so it
		// still renders nothing today. Same outcome as an unrecognised name.
		vi.mocked(sectionFields).mockReturnValueOnce([
			{
				title: 'Test section',
				summary: 'tv-episodes',
				columns: [],
				fields: [fieldA],
				advanced: []
			}
		]);
		renderComponent(SchemaConfigForm, { props: { group: LAYOUT_GROUP, config: LAYOUT_CONFIG } });
		expect(screen.queryByTestId('settings-section-columns')).not.toBeInTheDocument();
		expect(screen.getByLabelText('Field A')).toBeInTheDocument();
	});
});
