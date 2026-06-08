<script lang="ts">
	import { ExternalLinkIcon } from '@lucide/svelte';

	type Person = {
		id: string;
		name: string;
		email: string;
		created_at: string;
	};

	type Company = {
		id: string;
		name: string;
		emails: string[];
		company_type: string;
		domain: string;
		city: string;
		created_at: string;
		people: Person[];
	};

	type CompanyType = {
		id: number;
		name: string;
		label: string;
	};

	type EmailStats = {
		total_sent: number;
		last_sent_at: string | null;
	};

	export type SelectedRecipient = {
		company_id: string;
		company_name: string;
		company_email: string;
		company_type: string;
	};

	let {
		companies,
		companyTypes,
		twentyBaseUrl = '',
		emailStats = {},
		selectedRecipients = $bindable([])
	}: {
		companies: Company[];
		companyTypes: CompanyType[];
		twentyBaseUrl?: string;
		emailStats?: Record<string, EmailStats>;
		selectedRecipients: SelectedRecipient[];
	} = $props();

	function getHeatColor(dateStr: string | null | undefined): string {
		if (!dateStr) return 'text-surface-400';
		const now = Date.now();
		const sent = new Date(dateStr).getTime();
		const days = (now - sent) / (1000 * 60 * 60 * 24);
		if (days < 7) return 'text-green-600';
		if (days < 30) return 'text-yellow-600';
		if (days < 90) return 'text-orange-500';
		if (days < 180) return 'text-red-500';
		if (days < 365) return 'text-red-700';
		return 'text-red-900';
	}

	function companySentCount(company: Company): number {
		let total = emailStats[company.id]?.total_sent ?? 0;
		for (const p of company.people ?? []) {
			total += emailStats[p.id]?.total_sent ?? 0;
		}
		return total;
	}

	function companyLastSent(company: Company): string | null {
		let last = emailStats[company.id]?.last_sent_at ?? null;
		for (const p of company.people ?? []) {
			const pl = emailStats[p.id]?.last_sent_at;
			if (pl && (!last || new Date(pl).getTime() > new Date(last).getTime())) {
				last = pl;
			}
		}
		return last;
	}

	let search = $state('');
	let typeFilter = $state('');
	let noEmailOnly = $state(false);

	function hasNoEmail(company: Company): boolean {
		if (company.emails.length > 0) return false;
		return !(company.people ?? []).some((p) => p.email);
	}
	let sortField = $state<'created_at' | 'last_sent' | 'sent_count'>('created_at');
	let sortDesc = $state(true);

	function toggleSort(field: 'created_at' | 'last_sent' | 'sent_count') {
		if (sortField === field) {
			sortDesc = !sortDesc;
		} else {
			sortField = field;
			sortDesc = true;
		}
	}

	let filtered = $derived.by(() => {
		let result = companies;
		if (search) {
			const q = search.toLowerCase();
			result = result.filter(
				(c) =>
					c.name.toLowerCase().includes(q) ||
					c.emails.some((e) => e.toLowerCase().includes(q)) ||
					c.city.toLowerCase().includes(q)
			);
		}
		if (typeFilter) {
			result = result.filter((c) => c.company_type === typeFilter);
		}
		if (noEmailOnly) {
			result = result.filter((c) => hasNoEmail(c));
		}
		result = [...result].sort((a, b) => {
			if (sortField === 'sent_count') {
				const ca = companySentCount(a);
				const cb = companySentCount(b);
				return sortDesc ? cb - ca : ca - cb;
			}
			if (sortField === 'last_sent') {
				const la = companyLastSent(a);
				const lb = companyLastSent(b);
				const da = la ? new Date(la).getTime() : 0;
				const db = lb ? new Date(lb).getTime() : 0;
				return sortDesc ? db - da : da - db;
			}
			const da = new Date(a.created_at).getTime();
			const db = new Date(b.created_at).getTime();
			return sortDesc ? db - da : da - db;
		});
		return result;
	});

	let selectedKeys = $derived(
		new Set(selectedRecipients.map((r) => `${r.company_id}:${r.company_email}`))
	);

	function recipientKey(r: { company_id: string; company_email: string }): string {
		return `${r.company_id}:${r.company_email}`;
	}

	function companyRecipients(company: Company): SelectedRecipient[] {
		const recips: SelectedRecipient[] = [];
		const seen = new Set<string>();
		for (const e of company.emails) {
			if (seen.has(e)) continue;
			seen.add(e);
			recips.push({
				company_id: company.id,
				company_name: company.name,
				company_email: e,
				company_type: company.company_type
			});
		}
		for (const p of company.people ?? []) {
			if (p.email && !seen.has(p.email)) {
				seen.add(p.email);
				recips.push({
					company_id: p.id,
					company_name: company.name,
					company_email: p.email,
					company_type: company.company_type
				});
			}
		}
		return recips;
	}

	let allFilteredSelected = $derived.by(() => {
		const keys = filtered.flatMap((c) => companyRecipients(c).map(recipientKey));
		return keys.length > 0 && keys.every((k) => selectedKeys.has(k));
	});

	function toggleEmail(company: Company, email: string) {
		const key = `${company.id}:${email}`;
		if (selectedKeys.has(key)) {
			selectedRecipients = selectedRecipients.filter(
				(r) => !(r.company_id === company.id && r.company_email === email)
			);
		} else {
			selectedRecipients = [
				...selectedRecipients,
				{
					company_id: company.id,
					company_name: company.name,
					company_email: email,
					company_type: company.company_type
				}
			];
		}
	}

	function togglePerson(company: Company, person: Person) {
		const key = `${person.id}:${person.email}`;
		if (selectedKeys.has(key)) {
			selectedRecipients = selectedRecipients.filter(
				(r) => !(r.company_id === person.id && r.company_email === person.email)
			);
		} else {
			selectedRecipients = [
				...selectedRecipients,
				{
					company_id: person.id,
					company_name: company.name,
					company_email: person.email,
					company_type: company.company_type
				}
			];
		}
	}

	function toggleCompany(company: Company) {
		const recips = companyRecipients(company);
		if (recips.length === 0) return;
		const keys = recips.map(recipientKey);
		const allSelected = keys.every((k) => selectedKeys.has(k));
		if (allSelected) {
			const keySet = new Set(keys);
			selectedRecipients = selectedRecipients.filter((r) => !keySet.has(recipientKey(r)));
		} else {
			const existingKeys = new Set(selectedRecipients.map(recipientKey));
			const toAdd = recips.filter((r) => !existingKeys.has(recipientKey(r)));
			selectedRecipients = [...selectedRecipients, ...toAdd];
		}
	}

	function toggleAll() {
		const allRecips = filtered.flatMap(companyRecipients);
		if (allRecips.length === 0) return;
		const keys = allRecips.map(recipientKey);
		const allSelected = keys.every((k) => selectedKeys.has(k));
		if (allSelected) {
			const keySet = new Set(keys);
			selectedRecipients = selectedRecipients.filter((r) => !keySet.has(recipientKey(r)));
		} else {
			const existingKeys = new Set(selectedRecipients.map(recipientKey));
			const toAdd = allRecips.filter((r) => !existingKeys.has(recipientKey(r)));
			selectedRecipients = [...selectedRecipients, ...toAdd];
		}
	}

	function isCompanyFullySelected(company: Company) {
		const keys = companyRecipients(company).map(recipientKey);
		return keys.length > 0 && keys.every((k) => selectedKeys.has(k));
	}

	function isCompanyPartiallySelected(company: Company) {
		const keys = companyRecipients(company).map(recipientKey);
		return keys.some((k) => selectedKeys.has(k)) && !isCompanyFullySelected(company);
	}
</script>

<div class="space-y-4">
	<div class="flex flex-col sm:flex-row gap-3">
		<input
			type="search"
			placeholder="Search by name, email, city..."
			class="input flex-1"
			bind:value={search}
		/>
		<select class="select w-48" bind:value={typeFilter}>
			<option value="">All types</option>
			{#each companyTypes as ct}
				<option value={ct.name}>{ct.label}</option>
			{/each}
		</select>
		<label class="flex items-center gap-2 whitespace-nowrap">
			<input type="checkbox" class="checkbox" bind:checked={noEmailOnly} />
			<span class="text-sm">No email only</span>
		</label>
	</div>

	<div class="text-sm text-surface-600">
		{selectedRecipients.length} email(s) selected / {filtered.length} companies shown
	</div>

	<div class="table-container">
		<table class="table">
			<thead>
				<tr>
					<th>
						<input
							type="checkbox"
							checked={allFilteredSelected}
							onchange={toggleAll}
						/>
					</th>
					<th>Name</th>
					<th>Email(s)</th>
					<th>Type</th>
					<th class="hidden md:table-cell">
						<button
							type="button"
							class="text-sm font-bold text-surface-500 hover:text-surface-900 transition-colors whitespace-nowrap"
							onclick={() => toggleSort('sent_count')}
						>
							Sent{sortField === 'sent_count' ? (sortDesc ? ' ↓' : ' ↑') : ''}
						</button>
					</th>
					<th class="hidden md:table-cell">
						<button
							type="button"
							class="text-sm font-bold text-surface-500 hover:text-surface-900 transition-colors whitespace-nowrap"
							onclick={() => toggleSort('last_sent')}
						>
							Last email{sortField === 'last_sent' ? (sortDesc ? ' ↓' : ' ↑') : ''}
						</button>
					</th>
					<th class="hidden lg:table-cell">City</th>
					<th class="hidden lg:table-cell">Domain</th>
					<th class="hidden lg:table-cell">
						<button
							type="button"
							class="text-sm font-bold text-surface-500 hover:text-surface-900 transition-colors"
							onclick={() => toggleSort('created_at')}
						>
							Created at {sortField === 'created_at' ? (sortDesc ? '↓' : '↑') : ''}
						</button>
					</th>
					{#if twentyBaseUrl}
						<th class="hidden lg:table-cell">CRM</th>
					{/if}
				</tr>
			</thead>
			<tbody>
				{#each filtered as company (company.id)}
					<tr
						class="cursor-pointer hover:preset-tonal-primary"
						onclick={() => toggleCompany(company)}
					>
						<td>
							<input
								type="checkbox"
								checked={isCompanyFullySelected(company)}
								indeterminate={isCompanyPartiallySelected(company)}
								onclick={(e: MouseEvent) => e.stopPropagation()}
								onchange={() => toggleCompany(company)}
							/>
						</td>
						<td>{company.name}</td>
						<td onclick={(e: MouseEvent) => e.stopPropagation()}>
							{#if company.emails.length === 0}
								<span class="text-surface-400">—</span>
							{:else if company.emails.length === 1}
								<label class="flex items-center gap-2">
									<input
										type="checkbox"
										checked={selectedKeys.has(`${company.id}:${company.emails[0]}`)}
										onchange={() => toggleEmail(company, company.emails[0])}
									/>
									<span>{company.emails[0]}</span>
								</label>
							{:else}
								<div class="flex flex-col gap-1">
									{#each company.emails as email}
										<label class="flex items-center gap-2">
											<input
												type="checkbox"
												checked={selectedKeys.has(`${company.id}:${email}`)}
												onchange={() => toggleEmail(company, email)}
											/>
											<span>{email}</span>
										</label>
									{/each}
								</div>
							{/if}
						</td>
						<td>
							{#if company.company_type}
								<span class="badge preset-filled-surface-500 text-xs">{company.company_type}</span>
							{/if}
						</td>
						<td class="hidden md:table-cell text-center">
							{companySentCount(company)}
						</td>
						<td class="hidden md:table-cell whitespace-nowrap text-sm font-medium {getHeatColor(companyLastSent(company))}">
							{#if companyLastSent(company)}
								{new Date(companyLastSent(company)!).toLocaleDateString('fr-FR', {
									day: '2-digit',
									month: '2-digit',
									year: 'numeric'
								})}
							{:else}
								<span class="text-surface-400">—</span>
							{/if}
						</td>
						<td class="hidden lg:table-cell">{company.city || '—'}</td>
						<td class="hidden lg:table-cell">
							{#if company.domain}
								<a
									href={company.domain}
									target="_blank"
									rel="noopener"
									class="anchor"
									onclick={(e: MouseEvent) => e.stopPropagation()}
								>
									{company.domain.replace('https://', '')}
								</a>
							{:else}
								—
							{/if}
						</td>
						<td class="hidden lg:table-cell text-sm text-surface-600 whitespace-nowrap">
							{new Date(company.created_at).toLocaleDateString('fr-FR', {
								day: '2-digit',
								month: '2-digit',
								year: 'numeric',
								hour: '2-digit',
								minute: '2-digit'
							})}
						</td>
						{#if twentyBaseUrl}
							<td class="hidden lg:table-cell">
								<a
									href="{twentyBaseUrl}/object/company/{company.id}"
									target="_blank"
									rel="noopener"
									class="text-surface-500 hover:text-surface-900 transition-colors"
									title="Open in Twenty CRM"
									onclick={(e: MouseEvent) => e.stopPropagation()}
								>
									<ExternalLinkIcon class="size-4" />
								</a>
							</td>
						{/if}
					</tr>
					{#each company.people ?? [] as person, pi (person.id)}
						<tr
							class="cursor-pointer hover:preset-tonal-primary text-sm"
							onclick={() => togglePerson(company, person)}
						>
							<td></td>
							<td>
								<span class="text-surface-400 font-mono mr-1">
									{pi === company.people.length - 1 ? '└─' : '├─'}
								</span>
								{person.name || '—'}
							</td>
							<td onclick={(e: MouseEvent) => e.stopPropagation()}>
								{#if person.email}
									<label class="flex items-center gap-2">
										<input
											type="checkbox"
											checked={selectedKeys.has(`${person.id}:${person.email}`)}
											onchange={() => togglePerson(company, person)}
										/>
										<span>{person.email}</span>
									</label>
								{:else}
									<span class="text-surface-400">—</span>
								{/if}
							</td>
							<td>
								<span class="badge preset-filled-tertiary-500 text-xs">People</span>
							</td>
							<td class="hidden md:table-cell text-center">
								{emailStats[person.id]?.total_sent ?? 0}
							</td>
							<td class="hidden md:table-cell whitespace-nowrap text-sm font-medium {getHeatColor(emailStats[person.id]?.last_sent_at)}">
								{#if emailStats[person.id]?.last_sent_at}
									{new Date(emailStats[person.id].last_sent_at!).toLocaleDateString('fr-FR', {
										day: '2-digit',
										month: '2-digit',
										year: 'numeric'
									})}
								{:else}
									<span class="text-surface-400">—</span>
								{/if}
							</td>
							<td class="hidden lg:table-cell text-surface-400">—</td>
							<td class="hidden lg:table-cell text-surface-400">—</td>
							<td class="hidden lg:table-cell text-sm text-surface-600 whitespace-nowrap">
								{#if person.created_at}
									{new Date(person.created_at).toLocaleDateString('fr-FR', {
										day: '2-digit',
										month: '2-digit',
										year: 'numeric',
										hour: '2-digit',
										minute: '2-digit'
									})}
								{:else}
									<span class="text-surface-400">—</span>
								{/if}
							</td>
							{#if twentyBaseUrl}
								<td class="hidden lg:table-cell">
									<a
										href="{twentyBaseUrl}/object/person/{person.id}"
										target="_blank"
										rel="noopener"
										class="text-surface-500 hover:text-surface-900 transition-colors"
										title="Open in Twenty CRM"
										onclick={(e: MouseEvent) => e.stopPropagation()}
									>
										<ExternalLinkIcon class="size-4" />
									</a>
								</td>
							{/if}
						</tr>
					{/each}
				{:else}
					<tr>
						<td colspan="10" class="text-center text-surface-500">No companies found.</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
