// The label an ISO rip's preparing row shows for the ripper's phase.
import type { IsoSourceKind } from '$lib/api/dashboard';

const PHASE_LABELS: Record<string, string> = {
	scanning: 'Scanning image',
	extracting: 'Unpacking image'
};
const FOLDER_PHASE_LABELS: Record<string, string> = { scanning: 'Scanning disc folder' };

/**
 * The phase's label: a disc folder's own wording when it has one, else
 * the image wording, else the phase itself.
 */
export function isoPhaseLabel(phase: string, kind: IsoSourceKind): string {
	return (kind === 'folder' ? FOLDER_PHASE_LABELS[phase] : undefined) ?? PHASE_LABELS[phase] ?? phase;
}
