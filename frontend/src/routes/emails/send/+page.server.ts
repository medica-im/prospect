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

	const twentyBaseUrl = env.TWENTY_BASE_URL || '';

	return { companies, templates, companyTypes, twentyBaseUrl };
};
