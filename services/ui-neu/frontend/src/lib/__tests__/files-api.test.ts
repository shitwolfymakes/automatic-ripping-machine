import { describe, it, expect } from 'vitest';

import {
	fetchRoots, fetchDirectory, renameFile, moveFile,
	createDirectory, fixPermissions, deleteFile
} from '../api/files';

// The filesystem browser has no v3 backend (MISSING). Every function is a stub
// that rejects before any fetch; the Files screen is feature-flagged OFF.
describe('files MISSING stubs', () => {
	it('fetchRoots rejects', async () => {
		await expect(fetchRoots()).rejects.toThrow(/not yet available in v3/);
	});

	it('fetchDirectory rejects', async () => {
		await expect(fetchDirectory('/media/dir')).rejects.toThrow(/not yet available in v3/);
	});

	it('renameFile rejects', async () => {
		await expect(renameFile('/media/old.mkv', 'new.mkv')).rejects.toThrow(/not yet available in v3/);
	});

	it('moveFile rejects', async () => {
		await expect(moveFile('/media/file.mkv', '/archive/')).rejects.toThrow(/not yet available in v3/);
	});

	it('createDirectory rejects', async () => {
		await expect(createDirectory('/media', 'new-dir')).rejects.toThrow(/not yet available in v3/);
	});

	it('fixPermissions rejects', async () => {
		await expect(fixPermissions('/media/dir')).rejects.toThrow(/not yet available in v3/);
	});

	it('deleteFile rejects', async () => {
		await expect(deleteFile('/media/file.mkv')).rejects.toThrow(/not yet available in v3/);
	});
});
