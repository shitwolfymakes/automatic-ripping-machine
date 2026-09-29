import { describe, it, expect } from 'vitest';
import { createJob } from '../components/__fixtures__/job';
import { buildMetadataFields, parkedSessionLine, type MetadataField } from '../utils/job-fields';

function fieldLabels(fields: MetadataField[]): string[] {
	return fields.filter((f) => !f.empty).map((f) => f.label);
}

function findField(fields: MetadataField[], label: string): MetadataField | undefined {
	return fields.find((f) => f.label === label);
}

describe('buildMetadataFields', () => {
	describe('always-present fields', () => {
		it('includes base fields for any job', () => {
			const fields = buildMetadataFields(createJob());
			const labels = fieldLabels(fields);
			expect(labels).toContain('Disc Type');
			expect(labels).toContain('Status');
			expect(labels).toContain('Year');
			expect(labels).toContain('State');
		});

		it('Disc Type uses discTypeLabel', () => {
			const fields = buildMetadataFields(createJob({ disc_type: 'bluray' }));
			expect(findField(fields, 'Disc Type')?.value).toBe('Blu-ray');
		});

		it('Status shows the proper-cased status label', () => {
			const fields = buildMetadataFields(createJob({ status: 'ripped' }));
			expect(findField(fields, 'Status')?.value).toBe('Ripped');
		});

		it('Year shows the numeric year as a string', () => {
			const fields = buildMetadataFields(createJob({ year: 2025 }));
			expect(findField(fields, 'Year')?.value).toBe('2025');
		});

		it('Year shows dash when null', () => {
			const fields = buildMetadataFields(createJob({ year: null }));
			expect(findField(fields, 'Year')?.value).toBe('-');
		});
	});

	describe('rip progress', () => {
		it('includes a Tracks field when rip_progress is present', () => {
			const fields = buildMetadataFields(
				createJob({
					rip_progress: {
						tracks_total: 8,
						tracks_done: 3,
						tracks_failed: 0,
						current_track_id: null,
						current_track_index: null
					}
				})
			);
			expect(findField(fields, 'Tracks')?.value).toBe('3 / 8');
		});

		it('omits Tracks when rip_progress is null', () => {
			const fields = buildMetadataFields(createJob({ rip_progress: null }));
			expect(findField(fields, 'Tracks')).toBeUndefined();
		});
	});

	describe('state field based on job status', () => {
		it('shows In progress for active jobs', () => {
			const fields = buildMetadataFields(createJob({ status: 'ripping' }));
			expect(findField(fields, 'State')?.value).toBe('In progress');
		});

		it('shows Finished for failed jobs', () => {
			const fields = buildMetadataFields(createJob({ status: 'failed' }));
			expect(findField(fields, 'State')?.value).toBe('Finished');
		});

		it('shows In progress for a ripped job that is transcoding', () => {
			const fields = buildMetadataFields(
				createJob({
					status: 'ripped',
					transcode_progress: { state: 'transcoding', tasks_total: 1, tasks_done: 0, tasks_failed: 0, percent: 5 }
				})
			);
			expect(findField(fields, 'State')?.value).toBe('In progress');
		});
	});

	describe('padding to multiple of 4', () => {
		it('total length is a multiple of 4', () => {
			const fields = buildMetadataFields(createJob());
			expect(fields.length % 4).toBe(0);
		});

		it('padded fields have empty=true with blank label/value', () => {
			const fields = buildMetadataFields(createJob());
			const empties = fields.filter((f) => f.empty);
			for (const e of empties) {
				expect(e.label).toBe('');
				expect(e.value).toBe('');
			}
		});

		it('content fields do not have empty=true', () => {
			const fields = buildMetadataFields(createJob());
			const content = fields.filter((f) => !f.empty);
			expect(content.length).toBeGreaterThan(0);
			for (const f of content) {
				expect(f.label).not.toBe('');
			}
		});
	});
});

describe('buildMetadataFields — drive + crash', () => {
	it('includes the drive id', () => {
		const fields = buildMetadataFields(createJob({ drive_id: 'drv_ABC' }));
		const drive = fields.find((f) => f.label === 'Drive');
		expect(drive?.value).toBe('drv_ABC');
	});

	it('flags resumed_from_crash when true', () => {
		const fields = buildMetadataFields(createJob({ resumed_from_crash: true }));
		expect(fields.some((f) => f.label === 'Recovery' && f.value === 'Resumed from crash')).toBe(true);
	});

	it('omits the recovery field when not resumed', () => {
		const fields = buildMetadataFields(createJob({ resumed_from_crash: false }));
		expect(fields.some((f) => f.label === 'Recovery')).toBe(false);
	});
});

describe('parkedSessionLine', () => {
	const names = new Map([['ses_a', 'Plex 1080p']]);
	it('null when nothing is parked', () => {
		expect(parkedSessionLine({ status: 'identified', parked_session_ids: [] }, names)).toBeNull();
	});
	it('pre-rip: applies when the rip finishes', () => {
		expect(parkedSessionLine({ status: 'awaiting_review', parked_session_ids: ['ses_a'] }, names)).toBe(
			'Plex 1080p, applies when the rip finishes'
		);
	});
	it('post-rip: waiting, unknown ids shortened', () => {
		expect(
			parkedSessionLine({ status: 'ripped', parked_session_ids: ['ses_a', 'ses_0123456789abcdefXYZ'] }, names)
		).toBe('Plex 1080p, ses_0123456789a..., waiting');
	});
});

describe('buildMetadataFields session', () => {
	it('adds a Session field when a session is parked', () => {
		const fields = buildMetadataFields(
			createJob({ status: 'awaiting_review', parked_session_ids: ['ses_a'] }),
			null,
			new Map([['ses_a', 'Plex 1080p']])
		);
		expect(findField(fields, 'Session')?.value).toBe('Plex 1080p, applies when the rip finishes');
	});
});
