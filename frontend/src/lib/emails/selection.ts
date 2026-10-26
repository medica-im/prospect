// Recipient selection and filtering for the send page, kept free of Svelte so
// it can be unit tested. CompanyTable.svelte holds the state and calls these.
//
// Everything is per email address: a company's own addresses and its people's
// addresses are counted, filtered and selected one by one.

export type Person = {
	id: string;
	name: string;
	email: string;
	created_at: string;
};

export type Company = {
	id: string;
	name: string;
	emails: string[];
	company_type: string;
	domain: string;
	city: string;
	created_at: string;
	people: Person[];
};

export type EmailStats = {
	total_sent: number;
	last_sent_at: string | null;
};

/** Sent stats keyed by normalized address. */
export type AddressStats = Record<string, EmailStats>;

export type SelectedRecipient = {
	company_id: string; // the person's id for people
	company_name: string;
	company_email: string;
	company_type: string;
};

export type SortField = 'created_at' | 'last_sent' | 'sent_count';

export type CompanyView = {
	emails: string[]; // own addresses within the limit
	people: Person[]; // people with an address within the limit
	hidden: number; // addresses hidden by the limit
	sent: number; // company row: its own visible addresses
	last: string | null;
	groupSent: number; // company and people together, for sorting
	groupLastTime: number;
};

export const MAX_SENT_CEILING = 999;

export function normalize(email: string): string {
	return (email ?? '').trim().toLowerCase();
}

export function recipientKey(r: { company_id: string; company_email: string }): string {
	return `${r.company_id}:${r.company_email}`;
}

export function sentTo(stats: AddressStats, email: string): number {
	return stats[normalize(email)]?.total_sent ?? 0;
}

export function lastSentTo(stats: AddressStats, email: string): string | null {
	return stats[normalize(email)]?.last_sent_at ?? null;
}

/** maxSent is the most emails an address may already have received; null means no limit. */
export function withinLimit(stats: AddressStats, maxSent: number | null, email: string): boolean {
	return maxSent === null || sentTo(stats, email) <= maxSent;
}

// --- The "emails received" limit control ---

export function clampMaxSent(n: number | null): number | null {
	return n === null ? null : Math.min(MAX_SENT_CEILING, Math.max(0, Math.trunc(n)));
}

/**
 * "Any" sits below 0, so the first step up from no limit is 0 (never emailed),
 * the value wanted most often; a native number input would jump to 1.
 */
export function stepMaxSent(current: number | null, delta: 1 | -1): number | null {
	if (current === null) return delta > 0 ? 0 : null;
	if (current === 0 && delta < 0) return null;
	return clampMaxSent(current + delta);
}

/** Typed text to limit: digits only, at most three; empty means no limit. */
export function parseMaxSent(raw: string): { text: string; value: number | null } {
	const text = raw.replace(/\D/g, '').slice(0, 3);
	return { text, value: text === '' ? null : Number(text) };
}

// --- Recipients ---

/** Only people with an email are shown or selectable. */
export function peopleWithEmail(company: Company): Person[] {
	return (company.people ?? []).filter((p) => p.email);
}

export function hasNoEmail(company: Company): boolean {
	return company.emails.length === 0 && peopleWithEmail(company).length === 0;
}

/**
 * Selectable recipients of a company: its own addresses under the company id,
 * then its people under their own ids, each address once. Unsubscribed
 * addresses are left out here, which keeps them out of every bulk action.
 */
export function companyRecipients(
	company: Company,
	unsubscribed: Set<string>
): SelectedRecipient[] {
	const recips: SelectedRecipient[] = [];
	const seen = new Set<string>();
	const add = (id: string, email: string) => {
		const key = normalize(email);
		if (!email || seen.has(key) || unsubscribed.has(key)) return;
		seen.add(key);
		recips.push({
			company_id: id,
			company_name: company.name,
			company_email: email,
			company_type: company.company_type
		});
	};
	for (const e of company.emails) add(company.id, e);
	for (const p of company.people ?? []) add(p.id, p.email);
	return recips;
}

/** What the header and company checkboxes act on: recipients within the limit. */
export function bulkRecipients(
	recipients: SelectedRecipient[],
	stats: AddressStats,
	maxSent: number | null
): SelectedRecipient[] {
	return recipients.filter((r) => withinLimit(stats, maxSent, r.company_email));
}

/** Which of a company's addresses show under the limit, and the row figures. */
export function companyView(
	company: Company,
	stats: AddressStats,
	maxSent: number | null
): CompanyView {
	const within = (email: string) => withinLimit(stats, maxSent, email);
	const emails = company.emails.filter(within);
	const withEmail = peopleWithEmail(company);
	const people = withEmail.filter((p) => within(p.email));

	let sent = 0;
	let last: string | null = null;
	let lastTime = 0;
	for (const e of emails) {
		sent += sentTo(stats, e);
		const l = lastSentTo(stats, e);
		if (l && new Date(l).getTime() > lastTime) {
			last = l;
			lastTime = new Date(l).getTime();
		}
	}

	// The group total counts an address once even when a person shares it.
	let groupSent = sent;
	let groupLastTime = lastTime;
	const counted = new Set(emails.map(normalize));
	for (const p of people) {
		if (counted.has(normalize(p.email))) continue;
		counted.add(normalize(p.email));
		groupSent += sentTo(stats, p.email);
		const l = lastSentTo(stats, p.email);
		if (l) groupLastTime = Math.max(groupLastTime, new Date(l).getTime());
	}

	return {
		emails,
		people,
		hidden: company.emails.length - emails.length + withEmail.length - people.length,
		sent,
		last,
		groupSent,
		groupLastTime
	};
}

// --- Filtering and sorting ---

export function matchesSearch(company: Company, search: string): boolean {
	const q = search.toLowerCase();
	return (
		company.name.toLowerCase().includes(q) ||
		company.emails.some((e) => e.toLowerCase().includes(q)) ||
		company.city.toLowerCase().includes(q) ||
		(company.people ?? []).some(
			(p) =>
				(p.name ?? '').toLowerCase().includes(q) || (p.email ?? '').toLowerCase().includes(q)
		)
	);
}

/**
 * Every filter but the type, so the type buttons can count what each would
 * show. Under a limit a company stays only while it has a selectable address
 * within it.
 */
export function filterCompanies(
	companies: Company[],
	filters: { search: string; noEmailOnly: boolean; maxSent: number | null },
	bulkOf: (c: Company) => SelectedRecipient[]
): Company[] {
	let result = companies;
	if (filters.search) result = result.filter((c) => matchesSearch(c, filters.search));
	if (filters.noEmailOnly) result = result.filter(hasNoEmail);
	if (filters.maxSent !== null) result = result.filter((c) => bulkOf(c).length > 0);
	return result;
}

export function countByType(companies: Company[]): Map<string, number> {
	const counts = new Map<string, number>();
	for (const c of companies) counts.set(c.company_type, (counts.get(c.company_type) ?? 0) + 1);
	return counts;
}

export function sortCompanies(
	companies: Company[],
	field: SortField,
	desc: boolean,
	viewOf: (c: Company) => CompanyView
): Company[] {
	const value = (c: Company) =>
		field === 'sent_count'
			? viewOf(c).groupSent
			: field === 'last_sent'
				? viewOf(c).groupLastTime
				: new Date(c.created_at).getTime();
	return [...companies].sort((a, b) => (desc ? value(b) - value(a) : value(a) - value(b)));
}

// --- Selection ---

/**
 * Select mode: the selection is whatever the filters show, minus the
 * addresses unticked by hand, so changing a filter re-selects.
 */
export function selectModeSelection(
	shown: Company[],
	bulkOf: (c: Company) => SelectedRecipient[],
	excluded: Set<string>
): SelectedRecipient[] {
	return shown.flatMap((c) => bulkOf(c).filter((r) => !excluded.has(recipientKey(r))));
}

/** Select mode: ticking an address removes its exception, unticking adds one. */
export function updateExcluded(
	excluded: Set<string>,
	recipients: SelectedRecipient[],
	pick: boolean
): Set<string> {
	const next = new Set(excluded);
	for (const r of recipients) {
		if (pick) next.delete(recipientKey(r));
		else next.add(recipientKey(r));
	}
	return next;
}

/** Hand-made selection: add without duplicates, or remove. */
export function updateSelection(
	selected: SelectedRecipient[],
	recipients: SelectedRecipient[],
	pick: boolean
): SelectedRecipient[] {
	const selectedKeys = new Set(selected.map(recipientKey));
	if (pick) return [...selected, ...recipients.filter((r) => !selectedKeys.has(recipientKey(r)))];
	const drop = new Set(recipients.map(recipientKey));
	return selected.filter((r) => !drop.has(recipientKey(r)));
}

/** A hand-made selection loses its addresses over a newly committed limit. */
export function pruneOverLimit(
	selected: SelectedRecipient[],
	stats: AddressStats,
	maxSent: number | null
): SelectedRecipient[] {
	return selected.filter((r) => withinLimit(stats, maxSent, r.company_email));
}

/**
 * The header checkbox: it clears select mode, unticks a hand-made selection
 * that already covers everything shown, and otherwise enters select mode.
 */
export function headerCheckboxAction(
	selectMode: boolean,
	allShownSelected: boolean
): 'clear' | 'untick-shown' | 'enter-select-mode' {
	if (selectMode) return 'clear';
	if (allShownSelected) return 'untick-shown';
	return 'enter-select-mode';
}
