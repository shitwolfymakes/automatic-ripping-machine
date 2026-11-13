// How a failed preset save reads in the sidebar: marked settings for a 422 with an issue list,
// a missing-schema flag for a 503, else the shared save-error message.

import type { SettingIssue } from '$lib/types/api.gen';
import { ApiError, saveErrorMessage } from './client';

export const MARKED_ISSUES_MESSAGE = 'Fix the marked settings and save again.';

export interface SaveFailure {
	issues: SettingIssue[] | null;
	message: string;
	schemaMissing: boolean;
}

function issueList(body: unknown): SettingIssue[] | null {
	const detail = (body as { detail?: { issues?: unknown } } | null)?.detail;
	return Array.isArray(detail?.issues) ? (detail.issues as SettingIssue[]) : null;
}

export function saveFailure(e: unknown): SaveFailure {
	const issues = e instanceof ApiError && e.status === 422 ? issueList(e.body) : null;
	if (issues) return { issues, message: MARKED_ISSUES_MESSAGE, schemaMissing: false };
	const schemaMissing = e instanceof ApiError && e.status === 503;
	return { issues: null, message: saveErrorMessage(e), schemaMissing };
}
