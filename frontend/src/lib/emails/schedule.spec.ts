import { describe, expect, it } from 'vitest';
import { wallClockToInstant } from './schedule';

describe('wallClockToInstant', () => {
	it('reads Paris winter time as UTC+1', () => {
		expect(wallClockToInstant('2027-01-15T09:00', 'Europe/Paris')?.toISOString()).toBe(
			'2027-01-15T08:00:00.000Z'
		);
	});

	it('reads Paris summer time as UTC+2', () => {
		expect(wallClockToInstant('2027-07-15T09:00', 'Europe/Paris')?.toISOString()).toBe(
			'2027-07-15T07:00:00.000Z'
		);
	});

	it('honours another zone', () => {
		expect(wallClockToInstant('2027-01-15T09:00', 'America/Montreal')?.toISOString()).toBe(
			'2027-01-15T14:00:00.000Z'
		);
	});

	it('refuses a time skipped when clocks go forward', () => {
		expect(wallClockToInstant('2027-03-28T02:30', 'Europe/Paris')).toBeNull();
	});

	it('refuses malformed input and unknown zones', () => {
		expect(wallClockToInstant('tomorrow', 'Europe/Paris')).toBeNull();
		expect(wallClockToInstant('2027-01-15T09:00', 'Mars/Olympus')).toBeNull();
	});
});
