import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import FinishSummary from '../FinishSummary.svelte';

describe('FinishSummary', () => {
	afterEach(() => cleanup());
	it('words each step state and links back to it', () => {
		renderComponent(FinishSummary, {
			props: {
				view: {
					completed_at: null,
					current_step: 'finish',
					admin_default_password: false,
					checklist_dismissed: false,
					progress: { account: { state: 'done' }, system: { state: 'attention' }, notifications: { state: 'skipped' } }
				},
				summaries: { drives: '1 enrolled, 1 ignored' }
			}
		});
		expect(screen.getByTestId('finish-row-system')).toHaveTextContent('Needs attention');
		expect(screen.getByTestId('finish-row-notifications')).toHaveTextContent('Skipped');
		expect(screen.getByTestId('finish-row-drives')).toHaveTextContent('1 enrolled, 1 ignored');
		expect(screen.getByRole('link', { name: 'Edit System check' })).toHaveAttribute('href', '/setup/system');
		expect(screen.queryByTestId('finish-row-finish')).toBeNull();
	});
});
