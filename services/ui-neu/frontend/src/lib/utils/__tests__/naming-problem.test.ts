import { describe, expect, it } from 'vitest';
import { explainNamingProblem } from '../naming-problem';

const msg = (token: string) => `cannot resolve token {${token}} for job`;

const noPreset = (token: string) =>
	`This session has no transcode preset, so {${token}} in its output path cannot be filled. Give the session a transcode preset or choose another session.`;

const noValue = (what: string, token: string) =>
	`This job has no ${what}, so {${token}} in the output path cannot be filled. Add it in the job's details, or choose a session whose output path does not use it or marks it optional as {${token}?}.`;

describe('explainNamingProblem', () => {
	it.each(['transcode_slug', 'ext'])('tells the operator the session has no transcode preset for {%s}', (token) => {
		expect(explainNamingProblem(msg(token))).toBe(noPreset(token));
	});

	it.each([
		['title', 'title'],
		['year', 'year'],
		['show', 'show name'],
		['season', 'season'],
		['episode_title', 'episode title'],
		['artist', 'artist'],
		['album', 'album'],
		['disc', 'disc number'],
		['track_title', 'track titles']
	])('names what the job lacks for {%s}', (token, what) => {
		expect(explainNamingProblem(msg(token))).toBe(noValue(what, token));
	});

	it('strips the leading "an " from a word that starts with it', () => {
		expect(explainNamingProblem(msg('episode'))).toBe(noValue('episode number', 'episode'));
	});

	it('falls back to "a value for" for an unknown token', () => {
		expect(explainNamingProblem(msg('x'))).toBe(noValue('value for {x}', 'x'));
	});

	it('returns a message with no token as is', () => {
		expect(explainNamingProblem('Preview failed')).toBe('Preview failed');
	});
});
