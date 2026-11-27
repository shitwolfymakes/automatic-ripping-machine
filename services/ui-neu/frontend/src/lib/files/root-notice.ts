// The wording of the read-only banner on the Files page: the staging root is
// read-only because ARM itself writes and reads it, every other read-only root
// because of how it is mounted.
export const STAGING_ROOT_KEY = 'STAGING';

export function readonlyNotice(rootKey: string): string {
	if (rootKey === STAGING_ROOT_KEY) {
		return 'Staging is managed by ARM: transcodes read the staged copies here. You can browse it, but not change it.';
	}
	return 'This directory is on a read-only mount. File operations are disabled.';
}
