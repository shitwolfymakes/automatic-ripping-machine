// Pure rules behind the app header's status indicators; they also back the
// mobile stats panel.
import type { DashboardData } from '$lib/api/dashboard';

export function transcoderDotStatus(
	d: Pick<DashboardData, 'transcoder_online' | 'transcoder_stats'>
): 'ok' | 'warn' | 'off' {
	if (d.transcoder_online && (d.transcoder_stats?.worker_running ?? true)) return 'ok';
	return d.transcoder_online ? 'warn' : 'off';
}

/** One row of the mobile stats panel's service list. */
interface ServiceRow {
	label: string;
	href: string;
	status: 'ok' | 'warn' | 'error' | 'off';
}

/**
 * The service rows the mobile stats panel lists, each with its link and
 * status.
 */
export function serviceRows(
	d: Pick<DashboardData, 'arm_online' | 'db_available' | 'transcoder_online' | 'transcoder_stats' | 'makemkv_key_valid'>
): ServiceRow[] {
	return [
		{
			label: 'ARM',
			href: '/settings#system',
			status: d.arm_online ? 'ok' : 'error'
		},
		{
			label: 'DB',
			href: '/settings#system',
			status: d.db_available ? 'ok' : 'warn'
		},
		{
			label: 'Transcode',
			href: '/transcoder',
			status: transcoderDotStatus(d)
		},
		{
			label: 'Key',
			href: '/settings#Keys/makemkv_key',
			status: d.makemkv_key_valid === true ? 'ok' : 'error'
		}
	];
}

export function makemkvKeyTitle(valid: boolean | null, checkedAt: string | null): string {
	if (valid === true) {
		const suffix = checkedAt ? ' - checked ' + new Date(checkedAt).toLocaleString() : '';
		return `MakeMKV key valid${suffix}`;
	}
	return valid === false ? 'MakeMKV key invalid - click to update' : 'MakeMKV key not checked yet';
}
