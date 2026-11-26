import { describe, it, expect } from 'vitest';
import { bulkDeleteFeedback } from '$lib/dashboard/bulk-delete-feedback';

const response = (deleted: string[], skipped: string[]) =>
	({ deleted_ids: deleted, skipped_non_terminal: skipped }) as any;

describe('bulkDeleteFeedback', () => {
	it('reports a success when no job was skipped', () => {
		expect(bulkDeleteFeedback(response(['a', 'b'], []))).toEqual({
			type: 'success',
			message: 'Deleted 2 job(s)'
		});
	});

	it('reports an error naming the skipped in-flight jobs', () => {
		expect(bulkDeleteFeedback(response(['a'], ['b', 'c']))).toEqual({
			type: 'error',
			message: 'Deleted 1, skipped 2 in-flight job(s)'
		});
	});

	it('reports a success with zero deleted when nothing was deleted or skipped', () => {
		expect(bulkDeleteFeedback(response([], []))).toEqual({
			type: 'success',
			message: 'Deleted 0 job(s)'
		});
	});
});
