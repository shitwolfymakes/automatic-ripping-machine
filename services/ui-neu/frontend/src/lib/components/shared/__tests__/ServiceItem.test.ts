import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/test-utils';
import type { SystemDiagnosticCheck } from '$lib/types/api.gen';
import ServiceItem from '../ServiceItem.svelte';

const service = (over: Partial<SystemDiagnosticCheck> = {}): SystemDiagnosticCheck => ({
	name: 'transcoder',
	status: 'ok',
	...over
});

const renderCard = (check: SystemDiagnosticCheck) => {
	renderComponent(ServiceItem, { props: { check } });
	return screen.getByTestId('system-health-service');
};

describe('ServiceItem', () => {
	afterEach(() => cleanup());

	it('shows the ripper manager as ok with its label, description and badge', () => {
		const card = renderCard(service({ name: 'ripper_manager' }));
		expect(card).toHaveAttribute('data-status', 'ok');
		expect(within(card).getByText('Ripper service')).toBeInTheDocument();
		expect(within(card).getByText('ARM can start a ripper for each drive you enroll.')).toBeInTheDocument();
		expect(within(card).getByText('OK')).toBeInTheDocument();
	});

	it('shows the transcoder running on this server', () => {
		const card = renderCard(service({ location: 'local' }));
		expect(within(card).getByText('This server')).toBeInTheDocument();
	});

	it('shows the transcoder running on a remote host', () => {
		const card = renderCard(service({ location: 'remote', remote_host: 'nas' }));
		expect(within(card).getByText('Remote host nas')).toBeInTheDocument();
	});

	it('shows an install that only rips', () => {
		const card = renderCard(service({ location: 'none' }));
		expect(within(card).getByText('Ripper only')).toBeInTheDocument();
	});

	it('shows no location chip when the service has no location', () => {
		const card = renderCard(service());
		expect(within(card).queryByText('This server')).toBeNull();
		expect(within(card).queryByText('Ripper only')).toBeNull();
		expect(within(card).queryByText(/Remote host/)).toBeNull();
	});

	it('shows a passing detail by its label and a failing one as a problem', () => {
		const card = renderCard(
			service({
				details: [
					{ label: 'Docker socket', ok: true },
					{ label: 'Image', ok: false }
				]
			})
		);
		expect(within(card).getByText('Docker socket')).toBeInTheDocument();
		expect(within(card).getByText('Image: problem')).toBeInTheDocument();
	});

	it('shows no detail chips when the check has no details', () => {
		const card = renderCard(service());
		expect(within(card).queryByText(/problem/)).toBeNull();
	});

	it('shows the detail line for a service that is not ok', () => {
		const card = renderCard(service({ status: 'error', detail: 'socket missing' }));
		expect(within(card).getByText('socket missing')).toBeInTheDocument();
		expect(within(card).getByText('Problem')).toBeInTheDocument();
	});

	it('hides the detail line for an ok service', () => {
		const card = renderCard(service({ detail: 'all good' }));
		expect(within(card).queryByText('all good')).toBeNull();
	});

	it('hides the detail line for a failing service without one', () => {
		const card = renderCard(service({ status: 'warning', detail: null }));
		expect(within(card).getByText('Problem')).toBeInTheDocument();
		expect(within(card).queryByText('null')).toBeNull();
	});
});
