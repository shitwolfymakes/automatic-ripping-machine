import { notAvailable } from './_stub';

// MISSING in v3: the BFF's filesystem browser (roots / list / rename / move /
// mkdir / fix-permissions / delete) has no v3 backend. The Files screen is
// feature-flagged OFF, so these stubs reject before any fetch. Function names
// are preserved so consumers still compile.
//
// Shapes the (dormant) Files UI reads are declared locally here and re-exported,
// since the generated api.gen no longer carries FileRoot / DirectoryListing /
// FileEntry.

export interface FileEntry {
	name: string;
	type: 'file' | 'directory';
	size?: number | null;
	modified?: string | null;
	extension?: string | null;
	category?: string;
	permissions?: string | null;
	owner?: string | null;
	group?: string | null;
}

export interface DirectoryListing {
	path: string;
	parent?: string | null;
	readonly?: boolean;
	entries: FileEntry[];
}

export interface FileRoot {
	key?: string;
	path: string;
	label: string;
	host_path?: string | null;
}

export async function fetchRoots(): Promise<FileRoot[]> {
	notAvailable('File browser roots');
}

export async function fetchDirectory(_path: string): Promise<DirectoryListing> {
	notAvailable('File browser directory listing');
}

export async function renameFile(
	_path: string,
	_newName: string
): Promise<{ success: boolean; new_path: string }> {
	notAvailable('File rename');
}

export async function moveFile(
	_path: string,
	_destination: string
): Promise<{ success: boolean; new_path: string }> {
	notAvailable('File move');
}

export async function createDirectory(
	_path: string,
	_name: string
): Promise<{ success: boolean; new_path: string }> {
	notAvailable('Create directory');
}

export async function fixPermissions(_path: string): Promise<{ success: boolean; fixed: number }> {
	notAvailable('Fix file permissions');
}

export async function deleteFile(_path: string): Promise<{ success: boolean }> {
	notAvailable('File delete');
}
