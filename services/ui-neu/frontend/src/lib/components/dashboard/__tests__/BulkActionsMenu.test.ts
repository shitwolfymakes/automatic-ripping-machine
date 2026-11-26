import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import BulkActionsMenu from '../BulkActionsMenu.svelte';

afterEach(cleanup);

function renderMenu(props: { selectedJobs?: Set<string>; bulkBusy?: boolean } = {}) {
	const onaction = vi.fn();
	renderComponent(BulkActionsMenu, {
		props: { selectedJobs: props.selectedJobs ?? new Set<string>(), bulkBusy: props.bulkBusy ?? false, onaction }
	});
	return { onaction, trigger: screen.getByRole('button', { name: /Actions/ }) };
}

describe('BulkActionsMenu', () => {
	it('uses the standard button size and a typed button', () => {
		const { trigger } = renderMenu();
		expect(trigger).toHaveClass('btn');
		expect(trigger).not.toHaveClass('chip');
		expect(trigger).toHaveAttribute('type', 'button');
	});

	it('reports its open state on the trigger', async () => {
		const { trigger } = renderMenu();
		expect(trigger).toHaveAttribute('aria-expanded', 'false');
		await fireEvent.click(trigger);
		expect(trigger).toHaveAttribute('aria-expanded', 'true');
	});

	it('bulk-deletes by status and closes', async () => {
		const { onaction, trigger } = renderMenu();
		await fireEvent.click(trigger);
		expect(screen.queryByText(/^Selected/)).toBeNull();
		await fireEvent.click(await screen.findByText('Delete All Successful'));
		expect(onaction).toHaveBeenCalledWith('delete', { status: 'ripped' }, 'delete all successful jobs');
		expect(trigger).toHaveAttribute('aria-expanded', 'false');
	});

	it('offers Delete Selected with the selection count', async () => {
		const { onaction, trigger } = renderMenu({ selectedJobs: new Set(['a', 'b']) });
		await fireEvent.click(trigger);
		expect(screen.getByText('Selected (2)')).toBeInTheDocument();
		await fireEvent.click(screen.getByText('Delete Selected'));
		expect(onaction).toHaveBeenCalledWith('delete', { job_ids: ['a', 'b'] }, 'delete 2 selected job(s)');
	});

	it('shows a spinner and is disabled while busy', () => {
		const { trigger } = renderMenu({ bulkBusy: true });
		expect(trigger).toBeDisabled();
		expect(trigger.querySelector('.bulk-actions-spinner')).not.toBeNull();
	});
});
