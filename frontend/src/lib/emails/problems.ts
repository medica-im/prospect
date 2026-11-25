// Addresses that are in Twenty right now and whose latest send did not get
// through (/api/emails/current-problems). Kept free of Svelte so it can be unit
// tested; the /emails/problems page renders it.

import { deliveryLook, type Tone } from './delivery';

export type Severity = 'dead' | 'troublesome' | 'pending';

/** What to do about an address: remove it from Twenty, look at it, retry later, or fix our side. */
export type Action = 'remove' | 'review' | 'retry' | 'fix';

export type CurrentProblem = {
	address: string;
	person_id: string;
	person_name: string;
	job_title: string;
	company_id: string;
	company_name: string;
	company_type: string;
	where: 'person_primary' | 'person_additional' | 'company';
	status: string;
	severity: Severity;
	action: Action;
	reason: string;
	bounce_class: string;
	smtp_detail: string;
	attempts: number;
	first_sent_at: string;
	first_problem_at: string | null;
	last_attempt_at: string;
	twenty_url: string;
};

export type CurrentProblems = {
	snapshot_at: string;
	count: number;
	rows: CurrentProblem[];
};

export type ActionFilter = Action | 'all';

export const ACTION_OPTIONS: { value: ActionFilter; label: string; hint: string }[] = [
	{
		value: 'remove',
		label: 'À supprimer',
		hint: "L'adresse est définitivement morte : à supprimer de Twenty."
	},
	{
		value: 'review',
		label: 'À vérifier',
		hint: 'Cause incertaine ou adresse peut-être valable : à regarder à la main.'
	},
	{
		value: 'retry',
		label: 'À réessayer',
		hint: "Problème temporaire (boîte pleine, serveur occupé) : garder l'adresse."
	},
	{
		value: 'fix',
		label: 'À corriger chez nous',
		hint: "Pas la faute de l'adresse : l'envoi a échoué de notre côté."
	},
	{ value: 'all', label: 'Toutes', hint: '' }
];

export const ACTION_TONE: Record<Action, Tone> = {
	remove: 'error',
	review: 'warning',
	retry: 'neutral',
	fix: 'neutral'
};

/** Why the advice is what it is, from the backend's `reason`. */
export const REASON_LABEL: Record<string, string> = {
	domain_gone: 'Domaine inexistant',
	mailbox_unknown: 'Boîte inexistante',
	account_closed: 'Compte désactivé ou fermé',
	spam_complaint: 'Plainte pour spam',
	mailbox_full: 'Boîte pleine',
	policy_block: 'Refusé par le serveur du destinataire',
	server_unreachable: 'Serveur de messagerie injoignable',
	retrying: 'Nouvelle tentative en cours',
	our_error: "Erreur de notre côté (modèle d'email)",
	suppressed_unknown: 'Exclue par Mailgun, cause inconnue',
	other: 'Autre échec'
};

export const WHERE_LABEL: Record<CurrentProblem['where'], string> = {
	person_primary: 'Personne (principale)',
	person_additional: 'Personne (supplémentaire)',
	company: 'Structure'
};

/** What went wrong, in the page's vocabulary: the bounce class when there is one, else the status. */
export function problemKind(row: Pick<CurrentProblem, 'bounce_class' | 'status'>): string {
	return row.bounce_class || row.status;
}

export function problemLabel(row: Pick<CurrentProblem, 'bounce_class' | 'status'>): string {
	if (row.status === 'send_failed') {
		return deliveryLook({ success: false, delivery_status: 'sent', bounce_class: '' }).label;
	}
	if (row.status === 'deferred') return 'En attente';
	return deliveryLook({
		success: true,
		delivery_status: row.status,
		bounce_class: row.bounce_class
	}).label;
}

export type ProblemFilters = {
	action: ActionFilter;
	/** A problemKind value, or '' for every kind. */
	kind: string;
	/** A Twenty company type, '' for every type. NO_TYPE selects the untyped. */
	companyType: string;
	search: string;
};

export const NO_TYPE = '(aucun)';

export function filterProblems(rows: CurrentProblem[], filters: ProblemFilters): CurrentProblem[] {
	const q = filters.search.trim().toLowerCase();
	return rows.filter((row) => {
		if (filters.action !== 'all' && row.action !== filters.action) return false;
		if (filters.kind && problemKind(row) !== filters.kind) return false;
		if (filters.companyType && (row.company_type || NO_TYPE) !== filters.companyType) return false;
		if (!q) return true;
		return [row.address, row.company_name, row.person_name].some((text) =>
			text.toLowerCase().includes(q)
		);
	});
}

export function countByAction(rows: CurrentProblem[]): Record<ActionFilter, number> {
	const counts: Record<ActionFilter, number> = {
		all: rows.length,
		remove: 0,
		review: 0,
		retry: 0,
		fix: 0
	};
	for (const row of rows) counts[row.action] += 1;
	return counts;
}

/** Rows per problemKind, most frequent first. */
export function countByKind(
	rows: CurrentProblem[]
): { kind: string; label: string; count: number }[] {
	const counts = new Map<string, { label: string; count: number }>();
	for (const row of rows) {
		const kind = problemKind(row);
		const entry = counts.get(kind) ?? { label: problemLabel(row), count: 0 };
		entry.count += 1;
		counts.set(kind, entry);
	}
	return [...counts]
		.map(([kind, { label, count }]) => ({ kind, label, count }))
		.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'fr'));
}

/** Company types present in the rows, for the filter. */
export function companyTypes(rows: CurrentProblem[]): string[] {
	return [...new Set(rows.map((row) => row.company_type || NO_TYPE))].sort((a, b) =>
		a.localeCompare(b, 'fr')
	);
}

export function formatDate(iso: string | null): string {
	if (!iso) return '';
	return new Date(iso).toLocaleDateString('fr-FR', {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric'
	});
}

export function formatDateTime(iso: string): string {
	return new Date(iso).toLocaleString('fr-FR', {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit'
	});
}
