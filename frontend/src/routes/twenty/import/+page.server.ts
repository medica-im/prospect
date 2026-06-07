import { env } from '$env/dynamic/private';
import type { PageServerLoad } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

export const load: PageServerLoad = async ({ cookies }) => {
	const headers: Record<string, string> = {};
	const sessionId = cookies.get('sessionid');
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;

	const [typesRes, transformersRes] = await Promise.all([
		fetch(`${API}/api/company-types`, { headers }),
		fetch(`${API}/api/twenty/transformers`, { headers })
	]);

	const companyTypes = typesRes.ok ? await typesRes.json() : [];
	const transformers = transformersRes.ok ? await transformersRes.json() : [];

	return { companyTypes, transformers };
};
