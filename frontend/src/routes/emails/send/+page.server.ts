import { env } from '$env/dynamic/private';
import { blockedLabel } from '$lib/emails/delivery';
import type { PageServerLoad } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

export const load: PageServerLoad = async ({ cookies }) => {
	const headers: Record<string, string> = {};
	const sessionId = cookies.get('sessionid');
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;

	const [companiesRes, templatesRes, typesRes, addressStatsRes, unsubRes, deadRes] = await Promise.all([
		fetch(`${API}/api/companies`, { headers }),
		fetch(`${API}/api/templates`, { headers }),
		fetch(`${API}/api/company-types`, { headers }),
		fetch(`${API}/api/email-stats/by-address`, { headers }),
		fetch(`${API}/api/unsubscribes`, { headers }),
		fetch(`${API}/api/emails/problem-addresses`, { headers })
	]);

	const companies = companiesRes.ok ? await companiesRes.json() : [];
	const templates = templatesRes.ok ? await templatesRes.json() : [];
	const companyTypes = typesRes.ok ? await typesRes.json() : [];
	const addressStats: Record<string, { total_sent: number; last_sent_at: string | null }> =
		addressStatsRes.ok ? await addressStatsRes.json() : {};
	const unsubscribed: string[] = unsubRes.ok
		? (await unsubRes.json()).map((u: { email: string }) => u.email)
		: [];

	// Addresses Mailgun says cannot be mailed (no mailbox, refused, spam complaint).
	// The send task refuses them too; this keeps them from being picked at all.
	const undeliverable: Record<string, string> = {};
	if (deadRes.ok) {
		for (const row of await deadRes.json()) {
			undeliverable[row.address.trim().toLowerCase()] = blockedLabel(row);
		}
	}

	const twentyBaseUrl = env.TWENTY_BASE_URL || '';

	return {
		companies,
		templates,
		companyTypes,
		twentyBaseUrl,
		addressStats,
		unsubscribed,
		undeliverable,
		loadedAt: new Date().toISOString()
	};
};
