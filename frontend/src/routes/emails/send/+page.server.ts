import { env } from '$env/dynamic/private';
import type { PageServerLoad } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

export const load: PageServerLoad = async ({ cookies }) => {
	const headers: Record<string, string> = {};
	const sessionId = cookies.get('sessionid');
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;

	const [companiesRes, templatesRes, typesRes] = await Promise.all([
		fetch(`${API}/api/companies`, { headers }),
		fetch(`${API}/api/templates`, { headers }),
		fetch(`${API}/api/company-types`, { headers })
	]);

	const companies = companiesRes.ok ? await companiesRes.json() : [];
	const templates = templatesRes.ok ? await templatesRes.json() : [];
	const companyTypes = typesRes.ok ? await typesRes.json() : [];

	// Fetch email stats for all companies
	let emailStats: Record<string, { total_sent: number; last_sent_at: string | null }> = {};
	if (companies.length > 0) {
		const ids = companies.map((c: { id: string }) => c.id).join(',');
		const statsRes = await fetch(`${API}/api/email-stats?twenty_crm_ids=${ids}`, { headers });
		if (statsRes.ok) {
			emailStats = await statsRes.json();
		}
	}

	const twentyBaseUrl = env.TWENTY_BASE_URL || '';

	return { companies, templates, companyTypes, twentyBaseUrl, emailStats };
};
