import { describe, it, expect } from 'vitest';
import {
	anglesFor,
	choiceEdits,
	gridMember,
	groupVersions,
	hasVersionSets,
	isVersionSet,
	otherMembers,
	parseTitleRef,
	targetFor,
	tickedMembers,
	versionChips,
	versionLine,
	versionSummary,
	viewsOf,
	type VersionSet
} from '../version-sets';
import { groupDecoys, refIndexOf } from '../title-class';
import { trackToRow, type ReviewRow } from '../review-rows';
import { bladeRunnerTracks } from '../../__fixtures__/version-sets';
import { createTrack } from '../../__fixtures__/job';
import type { TrackView } from '$lib/types/api.gen';

function rowsOf(tracks: TrackView[]): ReviewRow[] {
	const refIndex = refIndexOf(tracks);
	return tracks.map((t) => trackToRow(t, refIndex));
}

function setOf(tracks: TrackView[]): VersionSet {
	const found = groupVersions(rowsOf(tracks)).find(isVersionSet);
	if (!found) throw new Error('no set');
	return found;
}

/** Two angles of a 3D feature and a shorter copy, as on the real disc. */
function threeVersions(): TrackView[] {
	return bladeRunnerTracks().filter((t) => ['00334.mpls:1', '00334.mpls:2', '00342.mpls'].includes(t.source_ref));
}

describe('parseTitleRef', () => {
	it('reads a plain ref and an angle ref', () => {
		expect(parseTitleRef('00334.mpls')).toEqual({ source: '00334.mpls', angle: null });
		expect(parseTitleRef('00334.mpls:2')).toEqual({ source: '00334.mpls', angle: 2 });
	});
	it.each(['', ':2', '00334.mpls:', '00334.mpls:x', '00334.mpls:0'])('%j is malformed', (ref) => {
		expect(parseTitleRef(ref)).toBeNull();
	});
});

describe('groupVersions', () => {
	it('folds the alternates of a pick into one set at the pick position', () => {
		const items = groupVersions(rowsOf(bladeRunnerTracks()));
		const sets = items.filter(isVersionSet);
		expect(sets).toHaveLength(1);
		expect(sets[0].pickRef).toBe('00334.mpls:1');
		expect(sets[0].members.map((m) => [m.row.index, m.kind])).toEqual([
			[3, 'pick'],
			[4, 'angle'],
			[5, 'subset'],
			[6, 'view'],
			[7, 'variant'],
			[11, 'angle']
		]);
	});
	it('keeps every other row, in order, and none of the folded members', () => {
		const items = groupVersions(rowsOf(bladeRunnerTracks()));
		const flat = items.map((i) => (isVersionSet(i) ? `set:${i.pickRef}` : 'decoyGroup' in i ? 'decoys' : i.sourceRef));
		expect(flat).toEqual([
			'00095.mpls',
			'00096.mpls',
			'00102.mpls',
			'set:00334.mpls:1',
			'00400.mpls',
			'00103.mpls',
			'00500.mpls'
		]);
	});
	it('passes a decoy group through where it stands', () => {
		const rows = rowsOf(bladeRunnerTracks());
		const withGroup = groupDecoys(rows, 1);
		const items = groupVersions(withGroup);
		expect(items.some((i) => 'decoyGroup' in i)).toBe(true);
		expect(items.filter(isVersionSet)).toHaveLength(1);
	});
	it('leaves an alternate whose pick is not among the rows as an ordinary row', () => {
		const orphan = createTrack({
			id: 'x',
			index: 0,
			source_ref: 'a.mpls',
			title_class: 'angle',
			title_class_ref: 'gone'
		});
		const items = groupVersions(rowsOf([orphan]));
		expect(items.filter(isVersionSet)).toHaveLength(0);
		expect(items).toHaveLength(1);
	});
	it('makes no set of rows with no alternates', () => {
		const rows = rowsOf([createTrack({ id: 'a', index: 0, source_ref: '0', title_class: 'primary' })]);
		expect(groupVersions(rows).filter(isVersionSet)).toHaveLength(0);
	});
});

describe('axes', () => {
	const set = setOf(bladeRunnerTracks());
	it('lists the views present, and the angles of each view', () => {
		expect(viewsOf(set)).toEqual(['3d', '2d']);
		expect(anglesFor(set, '3d')).toEqual([1, 2]);
		expect(anglesFor(set, '2d')).toEqual([1, 2]);
	});
	it('leaves the subset and the variant off the grid', () => {
		expect(otherMembers(set).map((m) => m.row.index)).toEqual([5, 7]);
	});
	it('finds the member at a view and angle', () => {
		expect(gridMember(set, '3d', 2)?.row.index).toBe(4);
		expect(gridMember(set, '2d', 1)?.row.index).toBe(6);
		expect(gridMember(set, '2d', 3)).toBeNull();
	});
	it('picking 2D keeps the angle when the 2D view has it (D60: independent axes)', () => {
		const onAngle2 = set.members.find((m) => m.row.index === 4)!;
		expect(targetFor(set, onAngle2, { view: '2d' })?.row.index).toBe(11);
	});
	it('picking a view without the current angle falls to its first angle', () => {
		const twin = setOf([
			...threeVersions(),
			createTrack({
				id: 'v',
				index: 9,
				source_ref: '00343.mpls',
				title_class: 'view',
				title_class_ref: '00334.mpls:1',
				excluded: true
			})
		]);
		const onAngle2 = twin.members.find((m) => m.row.index === 4)!;
		expect(targetFor(twin, onAngle2, { view: '2d' })?.row.index).toBe(9);
	});
	it('picking an angle stays in the current view', () => {
		const angle1of2d = set.members.find((m) => m.row.index === 6)!;
		expect(targetFor(set, angle1of2d, { angle: 2 })?.row.index).toBe(11);
	});
	it('has no target for an angle the view lacks', () => {
		const pick = set.members[0];
		expect(targetFor(set, pick, { angle: 5 })).toBeNull();
	});
	it('a subset stands at its own view, angle 1', () => {
		const subset = set.members.find((m) => m.row.index === 5)!;
		expect(targetFor(set, subset, { angle: 2 })?.row.index).toBe(4);
	});
});

describe('labels', () => {
	const set = setOf(bladeRunnerTracks());
	const by = (index: number) => set.members.find((m) => m.row.index === index)!;
	it('chips: angle number and the view', () => {
		expect(versionChips(set, by(3))).toEqual(['Angle 1', '3D']);
		expect(versionChips(set, by(4))).toEqual(['Angle 2', '3D']);
		expect(versionChips(set, by(5))).toEqual(['3D']);
		expect(versionChips(set, by(6))).toEqual(['Angle 1', '2D']);
	});
	it('a set of one view and no angles has no chips', () => {
		const plain = setOf([
			createTrack({ id: 'a', index: 0, source_ref: 'a.mpls', title_class: 'primary' }),
			createTrack({
				id: 'b',
				index: 1,
				source_ref: 'b.mpls',
				title_class: 'subset',
				title_class_ref: 'a.mpls',
				expected_duration_seconds: 100
			})
		]);
		expect(plain.members.map((m) => versionChips(plain, m))).toEqual([[], []]);
	});
	it('a line says how the member differs from the pick', () => {
		expect(versionLine(set, by(3))).toBe('Main version');
		expect(versionLine(set, by(4))).toBe('Same film, other angle');
		expect(versionLine(set, by(5))).toBe('Same film, 1:49 shorter');
		expect(versionLine(set, by(6))).toBe('Same film in 2D');
		expect(versionLine(set, by(7))).toBe('Same film with an extra intro, 0:45 longer');
	});
	it('drops the difference when a length is unknown or not different', () => {
		const same = setOf([
			createTrack({ id: 'a', index: 0, source_ref: 'a.mpls', title_class: 'primary', expected_duration_seconds: 100 }),
			createTrack({
				id: 'b',
				index: 1,
				source_ref: 'b.mpls',
				title_class: 'subset',
				title_class_ref: 'a.mpls',
				expected_duration_seconds: 100
			}),
			createTrack({ id: 'c', index: 2, source_ref: 'c.mpls', title_class: 'variant', title_class_ref: 'a.mpls' })
		]);
		expect(versionLine(same, same.members[1])).toBe('Same film');
		expect(versionLine(same, same.members[2])).toBe('Same film with an extra intro');
	});
	it('a view line names the other dimension', () => {
		expect(versionLine(set, by(6))).toContain('2D');
		const threeD = setOf([
			createTrack({ id: 'a', index: 0, source_ref: 'a.mpls', title_class: 'primary' }),
			createTrack({
				id: 'b',
				index: 1,
				source_ref: 'b.mpls',
				title_class: 'view',
				title_class_ref: 'a.mpls',
				stereo_3d: true
			})
		]);
		expect(versionLine(threeD, threeD.members[1])).toBe('Same film in 3D');
	});
});

describe('versionSummary and ticks', () => {
	it('names the one kept version with its length and size', () => {
		const set = setOf(threeVersions());
		expect(versionSummary(set)).toBe('3 versions of the film: keeping #3 (Angle 1, 3D) 2h 43m 27s, ~37.3 GB');
	});
	it('names how many are kept when more than one is', () => {
		const tracks = threeVersions();
		tracks[1].excluded = false;
		expect(versionSummary(setOf(tracks))).toBe('3 versions of the film: keeping #3, #4');
	});
	it('says none is kept', () => {
		const tracks = threeVersions();
		tracks[0].excluded = true;
		expect(versionSummary(setOf(tracks))).toBe('3 versions of the film: none kept');
	});
	it('lists the ticked members', () => {
		expect(tickedMembers(setOf(threeVersions())).map((m) => m.row.index)).toEqual([3]);
	});
});

describe('choiceEdits', () => {
	it('ticks the chosen members and unticks the rest, in one list', () => {
		const set = setOf(threeVersions());
		expect(choiceEdits(set, ['trk_4'])).toEqual([
			{ track_id: 'trk_3', excluded: true },
			{ track_id: 'trk_4', excluded: false },
			{ track_id: 'trk_5', excluded: true }
		]);
	});
	it('ticks several', () => {
		const set = setOf(threeVersions());
		expect(choiceEdits(set, ['trk_3', 'trk_5']).map((e) => e.excluded)).toEqual([false, true, false]);
	});
});

describe('hasVersionSets', () => {
	it('is true when an alternate points at a title that is listed', () => {
		expect(hasVersionSets(bladeRunnerTracks())).toBe(true);
	});
	it('is false for a disc of single titles, and for an alternate of a missing title', () => {
		expect(hasVersionSets([createTrack({ id: 'a', index: 0, source_ref: '0', title_class: 'primary' })])).toBe(false);
		expect(
			hasVersionSets([
				createTrack({ id: 'a', index: 0, source_ref: '0', title_class: 'angle', title_class_ref: 'gone' })
			])
		).toBe(false);
		expect(hasVersionSets([])).toBe(false);
	});
	it('does not count a copy or a decoy as a version', () => {
		const tracks = [
			createTrack({ id: 'a', index: 0, source_ref: '0', title_class: 'primary' }),
			createTrack({ id: 'b', index: 1, source_ref: '1', title_class: 'duplicate', title_class_ref: '0' })
		];
		expect(hasVersionSets(tracks)).toBe(false);
	});
});
