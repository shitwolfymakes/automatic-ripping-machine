// Shared by SessionCard and PresetRow, which each carried their own copy.
export function humanizeOutputMode(v: string | null | undefined): string {
	switch (v) {
		case 'tracks':
			return 'Tracks';
		case 'iso':
			return 'ISO image';
		case 'data_copy':
			return 'File copy';
		case 'folder':
			return 'Disc backup (folder)';
		default:
			return v ?? '-';
	}
}
