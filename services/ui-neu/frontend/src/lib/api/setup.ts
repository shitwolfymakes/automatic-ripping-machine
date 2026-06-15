import { notAvailable } from './_stub';

// The setup wizard backend is absent in v3 (MISSING). The Setup screen is
// feature-flagged OFF, so these stubs reject before any fetch.
//
// SetupStatus is declared locally and re-exported; api.gen no longer carries it.
export interface SetupStatus {
	arm_version: string;
	db_initialized: boolean;
	db_exists?: boolean;
	db_current?: boolean;
	db_version?: string;
	db_head?: string;
	first_run?: boolean;
	setup_steps?: {
		drives?: number | string | null;
		[key: string]: number | string | null | undefined;
	} | null;
}

export async function fetchSetupStatus(): Promise<SetupStatus> {
	notAvailable('Setup status');
}

export async function completeSetup(): Promise<{ success: boolean }> {
	notAvailable('Complete setup');
}
