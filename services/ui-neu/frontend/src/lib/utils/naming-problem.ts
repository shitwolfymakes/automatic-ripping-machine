// What to tell the operator when a session's output path cannot be resolved
// for a job, from the token the server's naming error names.

const TOKEN_WORDS: Record<string, string> = {
	title: 'a title',
	year: 'a year',
	show: 'a show name',
	season: 'a season',
	episode: 'an episode number',
	episode_title: 'an episode title',
	artist: 'an artist',
	album: 'an album',
	disc: 'a disc number',
	track_title: 'track titles',
	transcode_slug: 'a transcode preset',
	ext: 'a transcode preset'
};

/** The sentence to show for a naming-preview failure `message`. */
export function explainNamingProblem(message: string): string {
	const m = /token \{(\w+)\}/.exec(message);
	const token = m ? m[1] : null;
	if (token === 'transcode_slug' || token === 'ext') {
		return `This session has no transcode preset, so {${token}} in its output path cannot be filled. Give the session a transcode preset or choose another session.`;
	}
	if (token) {
		const what = (TOKEN_WORDS[token] ?? `a value for {${token}}`).replace(/^an? /, '');
		return `This job has no ${what}, so {${token}} in the output path cannot be filled. Add it in the job's details, or choose a session whose output path does not use it or marks it optional as {${token}?}.`;
	}
	return message;
}
