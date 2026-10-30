// What became of a sent email, in words an operator can act on. Kept free of
// Svelte so it can be unit tested; the sent list and detail page render it.
//
// "Distribué" only means the recipient's mail server accepted the message. It
// does not prove the mailbox exists (catch-all domains accept everything), so
// nothing here ever calls an address "valide".

export type DeliveryFields = {
	success: boolean;
	delivery_status: string;
	bounce_class: string;
	delivery_detail?: string;
};

export type Tone = 'success' | 'warning' | 'error' | 'neutral';

export type DeliveryLook = {
	label: string;
	tone: Tone;
	/** The email needs a human look: a bad address to fix, or a failed send. */
	needsAction: boolean;
	explanation: string;
};

/** Skeleton badge classes per tone. Colour is never the only signal: the label always shows. */
export const TONE_CLASS: Record<Tone, string> = {
	success: 'preset-filled-success-500',
	warning: 'preset-filled-warning-500',
	error: 'preset-filled-error-500',
	neutral: 'preset-filled-surface-500'
};

export function deliveryLook(email: DeliveryFields): DeliveryLook {
	if (!email.success) {
		return {
			label: "Échec d'envoi",
			tone: 'error',
			needsAction: true,
			explanation: "Mailgun n'a pas accepté le message."
		};
	}
	switch (email.delivery_status) {
		case 'delivered':
			return {
				label: 'Distribué',
				tone: 'success',
				needsAction: false,
				explanation:
					"Le serveur du destinataire a accepté le message. Cela ne garantit pas que la boîte existe ni qu'il a été lu."
			};
		case 'deferred':
			return {
				label: 'Retardé',
				tone: 'warning',
				needsAction: false,
				explanation: 'Échec temporaire : Mailgun réessaie la distribution.'
			};
		case 'complained':
			return {
				label: 'Signalé comme spam',
				tone: 'error',
				needsAction: true,
				explanation:
					'Le destinataire a signalé ce message comme indésirable. Ne plus écrire à cette adresse.'
			};
		case 'suppressed':
			return {
				label: 'Refusé (liste d’exclusion)',
				tone: 'error',
				needsAction: true,
				explanation:
					"Mailgun a refusé l'envoi : cette adresse a déjà rebondi, s'est plainte ou s'est désinscrite."
			};
		case 'bounced':
			return bouncedLook(email.bounce_class);
		default:
			return {
				label: 'Envoyé',
				tone: 'neutral',
				needsAction: false,
				explanation: 'Accepté par Mailgun, pas encore de retour du serveur du destinataire.'
			};
	}
}

function bouncedLook(bounceClass: string): DeliveryLook {
	switch (bounceClass) {
		case 'mailbox_missing':
			return {
				label: 'Boîte inexistante',
				tone: 'error',
				needsAction: true,
				explanation:
					"Le serveur du destinataire dit que cette adresse n'existe pas. À corriger dans le CRM."
			};
		case 'domain_missing':
			return {
				label: 'Domaine inexistant',
				tone: 'error',
				needsAction: true,
				explanation:
					"Le domaine de l'adresse n'existe pas ou n'a pas de serveur de messagerie. À corriger dans le CRM."
			};
		case 'mailbox_full':
			return {
				label: 'Boîte pleine',
				tone: 'warning',
				needsAction: true,
				explanation: 'La boîte existe mais est pleine. Réessayer plus tard.'
			};
		case 'blocked':
			return {
				label: 'Rejeté (politique)',
				tone: 'warning',
				needsAction: true,
				explanation:
					"Le serveur du destinataire a refusé le message (spam ou règle de sécurité). L'adresse existe probablement."
			};
		default:
			return {
				label: 'Rejeté',
				tone: 'error',
				needsAction: true,
				explanation: 'Échec définitif de distribution. Voir le détail renvoyé par le serveur.'
			};
	}
}

// --- List filter ---

export type DeliveryFilter =
	| ''
	| 'problem'
	| 'dead'
	| 'rejected'
	| 'deferred'
	| 'delivered'
	| 'complained'
	| 'failed'
	| 'pending';

export const FILTER_OPTIONS: { value: DeliveryFilter; label: string }[] = [
	{ value: '', label: 'Tous les statuts' },
	{ value: 'problem', label: 'À vérifier' },
	{ value: 'dead', label: 'Adresse inexistante' },
	{ value: 'rejected', label: 'Rejetés' },
	{ value: 'complained', label: 'Signalés spam' },
	{ value: 'failed', label: "Échec d'envoi" },
	{ value: 'deferred', label: 'Retardés' },
	{ value: 'pending', label: 'Sans retour' },
	{ value: 'delivered', label: 'Distribués' }
];

export function isDead(email: DeliveryFields): boolean {
	return (
		email.success &&
		email.delivery_status === 'bounced' &&
		(email.bounce_class === 'mailbox_missing' || email.bounce_class === 'domain_missing')
	);
}

export function matchesFilter(email: DeliveryFields, filter: DeliveryFilter): boolean {
	switch (filter) {
		case '':
			return true;
		case 'problem':
			return deliveryLook(email).needsAction;
		case 'dead':
			return isDead(email);
		case 'rejected':
			return (
				email.success &&
				(email.delivery_status === 'suppressed' ||
					(email.delivery_status === 'bounced' && !isDead(email)))
			);
		case 'complained':
			return email.success && email.delivery_status === 'complained';
		case 'failed':
			return !email.success;
		case 'deferred':
			return email.success && email.delivery_status === 'deferred';
		case 'delivered':
			return email.success && email.delivery_status === 'delivered';
		case 'pending':
			return email.success && email.delivery_status === 'sent';
	}
}

export function countByFilter(emails: DeliveryFields[]): Record<DeliveryFilter, number> {
	const counts = {} as Record<DeliveryFilter, number>;
	for (const { value } of FILTER_OPTIONS) {
		counts[value] = emails.filter((e) => matchesFilter(e, value)).length;
	}
	return counts;
}

// --- Detail page ---

/** One line for a Mailgun event in the detail page timeline. */
export function eventLabel(kind: string, severity: string): string {
	if (kind === 'delivered') return 'Distribué au serveur du destinataire';
	if (kind === 'complained') return 'Signalé comme spam par le destinataire';
	if (kind === 'failed') {
		return severity === 'temporary' ? 'Échec temporaire (nouvelle tentative)' : 'Échec définitif';
	}
	return kind;
}

// --- Send picker ---

/** Short label for an address the send page refuses, from /emails/problem-addresses. */
export function blockedLabel(row: { delivery_status: string; bounce_class: string }): string {
	return deliveryLook({ success: true, ...row }).label;
}
