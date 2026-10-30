import { describe, expect, it } from 'vitest';
import {
	blockedLabel,
	countByFilter,
	deliveryLook,
	eventLabel,
	isDead,
	matchesFilter,
	type DeliveryFields
} from './delivery';

function email(delivery_status: string, bounce_class = '', success = true): DeliveryFields {
	return { success, delivery_status, bounce_class };
}

const missing = email('bounced', 'mailbox_missing');
const noDomain = email('bounced', 'domain_missing');
const full = email('bounced', 'mailbox_full');
const blocked = email('bounced', 'blocked');
const other = email('bounced', 'other');
const refused = email('suppressed');
const spam = email('complained');
const delayed = email('deferred');
const delivered = email('delivered');
const pending = email('sent');
const failed = email('sent', '', false);
const all = [missing, noDomain, full, blocked, other, refused, spam, delayed, delivered, pending, failed];

describe('deliveryLook', () => {
	it('names the problem for each kind of bounce', () => {
		expect(deliveryLook(missing).label).toBe('Boîte inexistante');
		expect(deliveryLook(noDomain).label).toBe('Domaine inexistant');
		expect(deliveryLook(full).label).toBe('Boîte pleine');
		expect(deliveryLook(blocked).label).toBe('Rejeté (politique)');
		expect(deliveryLook(other).label).toBe('Rejeté');
	});

	it('treats a send that Mailgun refused as a failure whatever the delivery status says', () => {
		expect(deliveryLook(failed).label).toBe("Échec d'envoi");
		expect(deliveryLook({ ...failed, delivery_status: 'delivered' }).tone).toBe('error');
	});

	it('only flags what needs a human', () => {
		const flagged = all.filter((e) => deliveryLook(e).needsAction);
		expect(flagged).toEqual([missing, noDomain, full, blocked, other, refused, spam, failed]);
	});

	it('never claims a delivered address is valid', () => {
		expect(deliveryLook(delivered).explanation).toContain('ne garantit pas');
		expect(deliveryLook(delivered).label).not.toMatch(/valide/i);
	});

	it('shows an unknown status as sent rather than crashing', () => {
		expect(deliveryLook(email('whatever')).label).toBe('Envoyé');
	});
});

describe('refused addresses from the problem list', () => {
	it('name the original bounce, not the refusal', () => {
		expect(deliveryLook(email('suppressed', 'mailbox_missing')).label).toBe('Boîte inexistante');
		expect(deliveryLook(email('suppressed')).label).toBe('Refusé (liste d’exclusion)');
	});
});

describe('filters', () => {
	it('dead is exactly the addresses to fix in the CRM', () => {
		expect(all.filter((e) => matchesFilter(e, 'dead'))).toEqual([missing, noDomain]);
		expect(isDead(full)).toBe(false);
		expect(isDead({ ...missing, success: false })).toBe(false);
	});

	it('rejected covers the other permanent failures and refusals', () => {
		expect(all.filter((e) => matchesFilter(e, 'rejected'))).toEqual([full, blocked, other, refused]);
	});

	it('every email is in exactly one of the exclusive buckets', () => {
		const buckets = ['dead', 'rejected', 'complained', 'failed', 'deferred', 'pending', 'delivered'] as const;
		for (const e of all) {
			expect(buckets.filter((b) => matchesFilter(e, b))).toHaveLength(1);
		}
	});

	it('counts per filter, with the empty filter matching everything', () => {
		const counts = countByFilter(all);
		expect(counts['']).toBe(all.length);
		expect(counts.problem).toBe(8);
		expect(counts.dead).toBe(2);
		expect(counts.delivered).toBe(1);
	});
});

describe('labels', () => {
	it('labels events and blocked addresses', () => {
		expect(eventLabel('failed', 'temporary')).toContain('temporaire');
		expect(eventLabel('failed', 'permanent')).toContain('définitif');
		expect(eventLabel('delivered', '')).toContain('Distribué');
		expect(blockedLabel({ delivery_status: 'bounced', bounce_class: 'mailbox_missing' })).toBe(
			'Boîte inexistante'
		);
		expect(blockedLabel({ delivery_status: 'complained', bounce_class: '' })).toBe(
			'Signalé comme spam'
		);
	});
});
