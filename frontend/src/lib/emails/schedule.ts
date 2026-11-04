/** The zone the operator's clients live in; the schedule form starts on it. */
export const DEFAULT_TIME_ZONE = 'Europe/Paris';

/** IANA zones for the picker, always including the default and UTC. */
export function timeZones(): string[] {
	let zones: string[] = [];
	try {
		zones = Intl.supportedValuesOf('timeZone');
	} catch {
		// Older engines lack supportedValuesOf; the two fixed entries still work.
	}
	return [...new Set([DEFAULT_TIME_ZONE, ...zones, 'UTC'])].sort();
}

/** Minutes `tz` is ahead of UTC at the instant `at`. */
function offsetMinutes(at: Date, tz: string): number {
	const parts = new Intl.DateTimeFormat('en-US', {
		timeZone: tz,
		hourCycle: 'h23',
		year: 'numeric',
		month: '2-digit',
		day: '2-digit',
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit'
	}).formatToParts(at);
	const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
	const wallAsUtc = Date.UTC(
		get('year'),
		get('month') - 1,
		get('day'),
		get('hour'),
		get('minute'),
		get('second')
	);
	return Math.round((wallAsUtc - Math.floor(at.getTime() / 1000) * 1000) / 60000);
}

/**
 * The instant a wall-clock time ("YYYY-MM-DDTHH:MM", as a datetime-local input
 * gives it) denotes in `tz`. Null when the input is malformed, the zone unknown,
 * or the time does not exist there (clocks going forward). Mirrors the
 * backend's check, so the form can warn before the server refuses.
 */
export function wallClockToInstant(local: string, tz: string): Date | null {
	const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(local);
	if (!m) return null;
	const wallAsUtc = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
	try {
		// Two passes: the offset must be read at the instant, which is what is sought.
		let guess = wallAsUtc - offsetMinutes(new Date(wallAsUtc), tz) * 60000;
		guess = wallAsUtc - offsetMinutes(new Date(guess), tz) * 60000;
		if (guess + offsetMinutes(new Date(guess), tz) * 60000 !== wallAsUtc) return null;
		return new Date(guess);
	} catch {
		return null;
	}
}

/** An instant shown in the viewer's own zone, to cross-check the chosen one. */
export function inBrowserZone(at: Date): string {
	return at.toLocaleString(undefined, {
		dateStyle: 'medium',
		timeStyle: 'short',
		timeZoneName: 'short'
	});
}
