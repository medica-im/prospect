import { describe, expect, it } from 'vitest';
import {
	NO_TYPE,
	companyTypes,
	countByKind,
	countByAction,
	filterProblems,
	formatDate,
	problemKind,
	problemLabel,
	type CurrentProblem,
	type ProblemFilters
} from './problems';

function row(overrides: Partial<CurrentProblem> = {}): CurrentProblem {
	return {
		address: 'a@x.example',
		person_id: 'p1',
		person_name: 'Ada Martin',
		job_title: 'Présidente',
		company_id: 'co-1',
		company_name: 'CPTS Val de Siagne',
		company_type: 'CPTS',
		where: 'person_primary',
		status: 'bounced',
		severity: 'dead',
		action: 'remove',
		reason: 'mailbox_unknown',
		bounce_class: 'mailbox_missing',
		smtp_detail: '550 5.1.1 no',
		attempts: 2,
		first_sent_at: '2026-01-10T09:00:00Z',
		first_problem_at: '2026-03-02T09:00:00Z',
		last_attempt_at: '2026-03-02T09:00:00Z',
		twenty_url: 'https://twenty.example/object/person/p1',
		...overrides
	};
}

const dead = row();
const domain = row({ address: 'b@y.example', bounce_class: 'domain_missing', company_type: 'MSP' });
const full = row({
	address: 'c@z.example',
	bounce_class: 'mailbox_full',
	severity: 'troublesome',
	action: 'retry',
	reason: 'mailbox_full',
	company_type: '',
	company_name: 'Cabinet Plein',
	person_name: ''
});
const refused = row({
	address: 'd@z.example',
	status: 'send_failed',
	bounce_class: '',
	severity: 'troublesome',
	action: 'fix',
	reason: 'our_error'
});
const deferred = row({
	address: 'e@z.example',
	status: 'deferred',
	bounce_class: '',
	severity: 'pending',
	action: 'retry',
	reason: 'retrying'
});
const suppressedUnknown = row({
	address: 'f@z.example',
	status: 'suppressed',
	bounce_class: '',
	action: 'review',
	reason: 'suppressed_unknown'
});
const all = [dead, domain, full, refused, deferred, suppressedUnknown];

const NONE: ProblemFilters = { action: 'all', kind: '', companyType: '', search: '' };
const addresses = (rows: CurrentProblem[]) => rows.map((r) => r.address);

describe('problemLabel and problemKind', () => {
	it('names the bounce class, or the status when there is no class', () => {
		expect(problemKind(dead)).toBe('mailbox_missing');
		expect(problemKind(refused)).toBe('send_failed');
		expect(problemLabel(dead)).toBe('Boîte inexistante');
		expect(problemLabel(domain)).toBe('Domaine inexistant');
		expect(problemLabel(full)).toBe('Boîte pleine');
		expect(problemLabel(refused)).toBe("Échec d'envoi");
		expect(problemLabel(suppressedUnknown)).toBe('Refusé (liste d’exclusion)');
	});

	it('calls a deferred send "en attente", not a problem with the address', () => {
		expect(problemLabel(deferred)).toBe('En attente');
	});
});

describe('filterProblems', () => {
	it('filters on the advised action', () => {
		expect(addresses(filterProblems(all, { ...NONE, action: 'remove' }))).toEqual([
			'a@x.example',
			'b@y.example'
		]);
		expect(addresses(filterProblems(all, { ...NONE, action: 'retry' }))).toEqual([
			'c@z.example',
			'e@z.example'
		]);
		expect(addresses(filterProblems(all, { ...NONE, action: 'fix' }))).toEqual(['d@z.example']);
		expect(filterProblems(all, NONE)).toHaveLength(6);
	});

	it('filters on problem kind and on company type', () => {
		expect(addresses(filterProblems(all, { ...NONE, kind: 'domain_missing' }))).toEqual([
			'b@y.example'
		]);
		expect(addresses(filterProblems(all, { ...NONE, kind: 'send_failed' }))).toEqual([
			'd@z.example'
		]);
		expect(addresses(filterProblems(all, { ...NONE, companyType: 'MSP' }))).toEqual([
			'b@y.example'
		]);
		expect(addresses(filterProblems(all, { ...NONE, companyType: NO_TYPE }))).toEqual([
			'c@z.example'
		]);
	});

	it('searches address, company and person without case or surrounding space', () => {
		expect(addresses(filterProblems(all, { ...NONE, search: ' B@Y.EXAMPLE ' }))).toEqual([
			'b@y.example'
		]);
		expect(addresses(filterProblems(all, { ...NONE, search: 'plein' }))).toEqual(['c@z.example']);
		expect(filterProblems(all, { ...NONE, search: 'ada' })).toHaveLength(5);
	});

	it('combines filters', () => {
		const filters = {
			action: 'remove' as const,
			kind: 'mailbox_missing',
			companyType: 'CPTS',
			search: 'a@'
		};
		expect(addresses(filterProblems(all, filters))).toEqual(['a@x.example']);
	});
});

describe('counts', () => {
	it('counts by action, with all as the total', () => {
		expect(countByAction(all)).toEqual({ all: 6, remove: 2, review: 1, retry: 2, fix: 1 });
	});

	it('counts by kind, most frequent first, then by label', () => {
		const counts = countByKind([...all, row({ address: 'g@x.example' })]);
		expect(counts[0]).toEqual({ kind: 'mailbox_missing', label: 'Boîte inexistante', count: 2 });
		// One row each from here on: ordered by French label.
		expect(counts.map((c) => c.kind).slice(1)).toEqual([
			'mailbox_full',
			'domain_missing',
			'send_failed',
			'deferred',
			'suppressed'
		]);
	});

	it('lists the company types present, the untyped as its own entry', () => {
		expect(companyTypes(all)).toEqual(['(aucun)', 'CPTS', 'MSP']);
	});
});

describe('formatDate', () => {
	it('formats day month year, and nothing for a missing date', () => {
		expect(formatDate('2026-03-02T09:00:00Z')).toBe('02/03/2026');
		expect(formatDate(null)).toBe('');
	});
});
