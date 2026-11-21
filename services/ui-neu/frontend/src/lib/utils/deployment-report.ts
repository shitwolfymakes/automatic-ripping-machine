// Builds the Markdown deployment report that Settings > System copies for
// bug reports: version, environment by group, containers, health, log levels.
import type {
	ContainerView,
	DiagnosticsServiceView,
	EnvVarView,
	SystemDiagnosticsResponse,
	SystemEnvironmentResponse
} from '$lib/types/api.gen';
import { checkDetail, checkLabel, pathDetail, pathState } from './system-health';

function yesNo(v: boolean | null): string {
	if (v === null) return 'unknown';
	return v ? 'yes' : 'no';
}

function varLine(v: EnvVarView): string {
	if (v.secret) return `${v.key}=${v.is_set ? '<set>' : '<not set>'}`;
	let line = `${v.key}=${v.value ?? ''}`;
	if (v.source === 'default') line += '  (default)';
	if (v.effective) line += `  · in use: ${v.effective.value} (Settings → ${v.effective.tab})`;
	return line;
}

function fence(lines: string[]): string[] {
	return ['```', ...lines, '```'];
}

function containerBlock(c: ContainerView): string[] {
	const state = c.state === null ? '' : ` (${c.state})`;
	const lines = [`image: ${c.image}`];
	if (c.network) lines.push(`network: ${c.network}`);
	if (c.docker_host) lines.push(`docker host: ${c.docker_host}`);
	if (c.mounts.length) {
		lines.push('mounts:', ...c.mounts.map((m) => `  ${m.host} → ${m.container} (${m.mode})`));
	}
	if (c.devices.length) lines.push('devices:', ...c.devices.map((d) => `  ${d}`));
	if (c.env.length) {
		lines.push('env:', ...c.env.map((e) => `  ${e.key}=${e.secret ? '<secret>' : (e.value ?? '')}`));
	}
	return [`<details><summary>${c.kind} — ${c.label}${state}</summary>`, '', ...fence(lines), '', '</details>'];
}

function healthSection(health: SystemDiagnosticsResponse): string[] {
	const lines = health.checks.map((c) =>
		c.status === 'ok' ? `- ✅ ${checkLabel(c.name)}` : `- ❌ ${checkLabel(c.name)}: ${checkDetail(c)}`
	);
	for (const p of health.paths) {
		lines.push(pathState(p) === 'ok' ? `- ✅ ${p.name}: ${p.path}` : `- ❌ ${p.name}: ${p.path}, ${pathDetail(p)}`);
	}
	return ['### Health', ...lines, ''];
}

export function buildDeploymentReport(
	env: SystemEnvironmentResponse,
	health: SystemDiagnosticsResponse | null,
	logLevels: DiagnosticsServiceView[],
	now: Date
): string {
	const out: string[] = [
		`## ARM deployment report — ${env.version} — ${now.toISOString()}`,
		'',
		'**Summary**',
		`- Host paths set: ${yesNo(env.summary.host_paths_set)}`,
		`- Transcode capable: ${yesNo(env.summary.transcode_capable)}`,
		`- GPUs: ${env.summary.gpus.length ? env.summary.gpus.join(', ') : 'none'}`,
		''
	];
	if (health) out.push(...healthSection(health));

	const levelLines = logLevels.map((s) => `- ${s.name}: ${s.log_level}`);
	let loggingDone = levelLines.length === 0;
	for (const g of env.groups) {
		out.push(`### ${g.name}`, ...fence(g.vars.map(varLine)));
		if (g.name === 'Logging' && !loggingDone) {
			out.push(...levelLines);
			loggingDone = true;
		}
		out.push('');
	}
	if (!loggingDone) out.push('### Logging', ...levelLines, '');

	if (env.containers.length) {
		out.push('### Containers', '');
		for (const c of env.containers) out.push(...containerBlock(c), '');
	}
	return out.join('\n').trimEnd() + '\n';
}
