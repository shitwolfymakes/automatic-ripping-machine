import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/testing/render';
import SchemaConfigForm from '../SchemaConfigForm.svelte';
import type { SettingsGroup, KeyCheckResponse } from '$lib/types/api.gen';

// Branch pins for SchemaConfigForm, beside SchemaConfigForm.test.ts. No
// branch is left open: every one is reached from the rendered component.

const saveArmConfig = vi.fn((_config: Record<string, unknown>) => Promise.resolve({ success: true }));
const checkApiKey = vi.fn((_name: string, _value?: string): Promise<KeyCheckResponse> =>
	Promise.resolve({ name: 'tmdb', status: 'ok', detail: null, checked_at: null })
);
vi.mock('$lib/api/settings', () => ({
	saveArmConfig: (config: Record<string, unknown>) => saveArmConfig(config),
	checkApiKey: (name: string, value?: string) => checkApiKey(name, value)
}));

const GROUP: SettingsGroup = {
	name: 'Metadata',
	fields: [
		{
			key: 'search_provider_movie',
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
const CONFIG = { search_provider_movie: 'tmdb', tmdb_api_key: '<hidden>', makemkv_key: '<hidden>' };

afterEach(() => {
	cleanup();
	saveArmConfig.mockClear();
	checkApiKey.mockReset();
	checkApiKey.mockResolvedValue({ name: 'tmdb', status: 'ok', detail: null, checked_at: null });
});

function testButton(key: string) {
	return within(screen.getByTestId(`setting-${key}`)).getByRole('button', { name: /^test$/i });
}

async function runCheck(key: string, result: KeyCheckResponse | Error | string) {
	if (typeof result === 'string' || result instanceof Error) checkApiKey.mockRejectedValue(result);
	else checkApiKey.mockResolvedValue(result);
	renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
	await fireEvent.click(testButton(key));
	await waitFor(() => expect(checkApiKey).toHaveBeenCalled());
}

describe('SchemaConfigForm key checks', () => {
	it('sends no key for a field that still holds the saved value', async () => {
		renderComponent(SchemaConfigForm, {
			props: { group: GROUP, config: { ...CONFIG, tmdb_api_key: 'saved-key' } }
		});
		await fireEvent.click(testButton('tmdb_api_key'));
		await waitFor(() => expect(checkApiKey).toHaveBeenCalledWith('tmdb', undefined));
	});

	it('shows the message of an Error the check rejects with', async () => {
		await runCheck('tmdb_api_key', new Error('socket closed'));
		await waitFor(() => expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent('socket closed'));
	});

	it('shows "check failed" when the check rejects with something that is not an Error', async () => {
		await runCheck('tmdb_api_key', 'boom');
		await waitFor(() => expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent('check failed'));
	});
});

describe('SchemaConfigForm key-check result line', () => {
	it('shows Key rejected without a detail line when the rejection has no detail', async () => {
		await runCheck('tmdb_api_key', { name: 'tmdb', status: 'invalid', detail: null, checked_at: null });
		const line = screen.getByTestId('key-check-tmdb_api_key');
		await waitFor(() => expect(line).toHaveTextContent('Key rejected'));
		expect(line.textContent?.trim()).toBe('Key rejected');
	});

	it('shows Key rejected with its detail', async () => {
		await runCheck('tmdb_api_key', { name: 'tmdb', status: 'invalid', detail: 'HTTP 401', checked_at: null });
		await waitFor(() => expect(screen.getByText('HTTP 401')).toBeInTheDocument());
		expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent('Key rejected');
	});

	it("shows Couldn't reach without a detail line when the failure has no detail", async () => {
		await runCheck('tmdb_api_key', { name: 'tmdb', status: 'error', detail: null, checked_at: null });
		const line = screen.getByTestId('key-check-tmdb_api_key');
		await waitFor(() => expect(line).toHaveTextContent("Couldn't reach TMDb"));
		expect(line.textContent?.trim()).toBe("Couldn't reach TMDb");
	});

	it("shows Couldn't reach with its detail", async () => {
		await runCheck('tmdb_api_key', { name: 'tmdb', status: 'error', detail: 'i/o timeout', checked_at: null });
		await waitFor(() => expect(screen.getByText('i/o timeout')).toBeInTheDocument());
		expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent("Couldn't reach TMDb");
	});

	it('shows the unknown status as its detail alone', async () => {
		await runCheck('tmdb_api_key', {
			name: 'tmdb',
			status: 'unknown',
			detail: 'the ripper verifies it',
			checked_at: null
		});
		await waitFor(() =>
			expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent('the ripper verifies it')
		);
		expect(screen.getByTestId('key-check-tmdb_api_key')).not.toHaveTextContent(/reach|rejected|works/i);
	});
});

describe('SchemaConfigForm clearing', () => {
	it('sends a cleared saved secret with no key check as null on save', async () => {
		const group: SettingsGroup = {
			name: 'Misc',
			fields: [
				{
					key: 'webhook_secret',
					group: 'Misc',
					tier: 'secret',
					label: 'Webhook secret',
					help: '',
					type: 'string',
					editable: true,
					enum_values: null
				}
			]
		};
		renderComponent(SchemaConfigForm, { props: { group, config: { webhook_secret: '<hidden>' } } });
		await fireEvent.click(
			within(screen.getByTestId('setting-webhook_secret')).getByRole('button', { name: /remove/i })
		);
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(saveArmConfig).toHaveBeenCalledWith({ webhook_secret: null }));
	});
});

describe('SchemaConfigForm config merge', () => {
	it('drops an unsaved edit when the group gets a new fields list, even with the same config', async () => {
		const { rerender } = renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		await fireEvent.change(screen.getByRole('combobox', { name: /provider/i }), { target: { value: 'omdb' } });
		await rerender({ group: { ...GROUP, fields: [...GROUP.fields] }, config: CONFIG });
		expect((screen.getByRole('combobox', { name: /provider/i }) as HTMLSelectElement).value).toBe('tmdb');
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(saveArmConfig).toHaveBeenCalledWith({}));
	});

	it("keeps the form's saved overrides across a new fields list with the same config", async () => {
		const { rerender } = renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
		const select = screen.getByRole('combobox', { name: /provider/i });
		await fireEvent.change(select, { target: { value: 'omdb' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(saveArmConfig).toHaveBeenCalledTimes(1));

		await rerender({ group: { ...GROUP, fields: [...GROUP.fields] }, config: CONFIG });
		await fireEvent.change(screen.getByRole('combobox', { name: /provider/i }), { target: { value: 'tmdb' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(saveArmConfig).toHaveBeenCalledTimes(2));
		expect(saveArmConfig.mock.calls[1][0]).toEqual({ search_provider_movie: 'tmdb' });
	});
});
