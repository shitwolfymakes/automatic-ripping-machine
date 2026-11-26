import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import { formatDateTime } from '$lib/utils/format';
import type { PreviousRipView } from '$lib/types/api.gen';
import PreviouslyRippedNotice from '../PreviouslyRippedNotice.svelte';

function earlier(overrides: Partial<PreviousRipView> = {}): PreviousRipView {
	return {
		job_id: 'job_old',
		title: 'Resident Evil',
		year: 2012,
		status: 'ripped',
		ripped_at: null,
		outputs_present: true,
		...overrides
	} as PreviousRipView;
}

function renderNotice(previous: PreviousRipView | null, loading = false) {
	renderComponent(PreviouslyRippedNotice, { props: { previous, loading } });
	return screen.getByTestId('previously-ripped');
}

describe('PreviouslyRippedNotice', () => {
	afterEach(cleanup);

	it('links the earlier rip by job id and title', () => {
		const notice = renderNotice(earlier());
		const link = screen.getByRole('link', { name: 'Resident Evil' });
		expect(link).toHaveAttribute('href', '/jobs/job_old');
		expect(notice).toHaveTextContent('ARM already ripped this disc as Resident Evil.');
	});

	it.each([null, '   '])('calls an earlier rip titled %j an untitled disc', (title) => {
		renderNotice(earlier({ title }));
		expect(screen.getByRole('link')).toHaveTextContent('an untitled disc');
	});

	it('shows the date after "on" when ripped_at is set', () => {
		const at = '2026-10-12T06:35:00Z';
		const notice = renderNotice(earlier({ ripped_at: at }));
		const text = notice.textContent?.replace(/\s+/g, ' ');
		expect(text).toContain('Resident Evil on ' + formatDateTime(at) + '.');
	});

	it('shows no date when ripped_at is missing', () => {
		const notice = renderNotice(earlier({ ripped_at: null }));
		expect(notice).not.toHaveTextContent(' on ');
	});

	it('ends with ", partially." for a partial rip', () => {
		const notice = renderNotice(earlier({ status: 'ripped_partial' }));
		expect(notice).toHaveTextContent('Resident Evil, partially.');
	});

	it('ends with "." for any other status', () => {
		const notice = renderNotice(earlier({ status: 'ripped' }));
		expect(notice).toHaveTextContent('Resident Evil.');
		expect(notice).not.toHaveTextContent('partially');
	});

	it.each([
		[true, 'Its files are still in the library.'],
		[false, 'Some of its files are no longer in the library.'],
		[null, 'It has no transcoded files.'],
		[undefined, 'It has no transcoded files.']
	])('says %s outputs_present as "%s"', (outputs_present, line) => {
		const notice = renderNotice(earlier({ outputs_present } as Partial<PreviousRipView>));
		expect(notice).toHaveTextContent(line);
	});

	it('says the earlier job was deleted when there is no previous rip and loading is done', () => {
		const notice = renderNotice(null, false);
		expect(notice).toHaveTextContent('ARM ripped this disc before, but that job has since been deleted.');
	});

	it('stays empty while the first load is still running', () => {
		const notice = renderNotice(null, true);
		expect(notice).toBeEmptyDOMElement();
	});
});
