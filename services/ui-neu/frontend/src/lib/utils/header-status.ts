// Pure rules behind the app header's status indicators.
import type { DashboardData } from '$lib/api/dashboard';

export function transcoderDotStatus(
	d: Pick<DashboardData, 'transcoder_online' | 'transcoder_stats'>
): 'ok' | 'warn' | 'off' {
	if (d.transcoder_online && (d.transcoder_stats?.worker_running ?? true)) return 'ok';
	return d.transcoder_online ? 'warn' : 'off';
}

export function makemkvKeyTitle(valid: boolean | null, checkedAt: string | null): string {
	if (valid === true) {
		const suffix = checkedAt ? ' - checked ' + new Date(checkedAt).toLocaleString() : '';
		return `MakeMKV key valid${suffix}`;
	}
	return valid === false ? 'MakeMKV key invalid - click to update' : 'MakeMKV key not checked yet';
}
