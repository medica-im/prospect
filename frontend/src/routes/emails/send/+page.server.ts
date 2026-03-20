import { env } from '$env/dynamic/private';
import type { PageServerLoad } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

export const load: PageServerLoad = async ({ fetch }) => {
	const [companiesRes, templatesRes, typesRes] = await Promise.all([
		fetch(`${API}/api/companies`),
		fetch(`${API}/api/templates`),
		fetch(`${API}/api/company-types`)
	]);

	const companies = companiesRes.ok ? await companiesRes.json() : [];
	const templates = templatesRes.ok ? await templatesRes.json() : [];
	const companyTypes = typesRes.ok ? await typesRes.json() : [];

	return { companies, templates, companyTypes };
};
