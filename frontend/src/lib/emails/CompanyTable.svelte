<script lang="ts">
	type Company = {
		id: string;
		name: string;
		emails: string[];
		company_type: string;
		domain: string;
		city: string;
	};

	type CompanyType = {
		id: number;
		name: string;
		label: string;
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
		selectedRecipients = $bindable([])
	}: {
		companies: Company[];
		companyTypes: CompanyType[];
		selectedRecipients: SelectedRecipient[];
	} = $props();

	let search = $state('');
	let typeFilter = $state('');

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
		return result;
	});

	let selectedKeys = $derived(
		new Set(selectedRecipients.map((r) => `${r.company_id}:${r.company_email}`))
	);

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

	function toggleCompany(company: Company) {
		const allSelected = company.emails.every((e) =>
			selectedKeys.has(`${company.id}:${e}`)
		);
		if (allSelected) {
			selectedRecipients = selectedRecipients.filter(
				(r) => r.company_id !== company.id
			);
		} else {
			const existing = selectedRecipients.filter(
				(r) => r.company_id !== company.id
			);
			const newEntries = company.emails.map((e) => ({
				company_id: company.id,
				company_name: company.name,
				company_email: e,
				company_type: company.company_type
			}));
			selectedRecipients = [...existing, ...newEntries];
		}
	}

	function toggleAll() {
		const allFilteredSelected = filtered.every((c) =>
			c.emails.length > 0 && c.emails.every((e) => selectedKeys.has(`${c.id}:${e}`))
		);
		if (allFilteredSelected) {
			const filteredIds = new Set(filtered.map((c) => c.id));
			selectedRecipients = selectedRecipients.filter(
				(r) => !filteredIds.has(r.company_id)
			);
		} else {
			const filteredIds = new Set(filtered.map((c) => c.id));
			const kept = selectedRecipients.filter((r) => !filteredIds.has(r.company_id));
			const newEntries = filtered.flatMap((c) =>
				c.emails.map((e) => ({
					company_id: c.id,
					company_name: c.name,
					company_email: e,
					company_type: c.company_type
				}))
			);
			selectedRecipients = [...kept, ...newEntries];
		}
	}

	function isCompanyFullySelected(company: Company) {
		return company.emails.length > 0 && company.emails.every((e) =>
			selectedKeys.has(`${company.id}:${e}`)
		);
	}

	function isCompanyPartiallySelected(company: Company) {
		return company.emails.some((e) =>
			selectedKeys.has(`${company.id}:${e}`)
		) && !isCompanyFullySelected(company);
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
							checked={filtered.length > 0 && filtered.every((c) => isCompanyFullySelected(c))}
							onchange={toggleAll}
						/>
					</th>
					<th>Name</th>
					<th>Email(s)</th>
					<th>Type</th>
					<th class="hidden lg:table-cell">City</th>
					<th class="hidden lg:table-cell">Domain</th>
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
					</tr>
				{:else}
					<tr>
						<td colspan="6" class="text-center text-surface-500">No companies found.</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
