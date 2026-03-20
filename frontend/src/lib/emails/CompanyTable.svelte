<script lang="ts">
	type Company = {
		id: string;
		name: string;
		email: string;
		company_type: string;
		domain: string;
		city: string;
	};

	type CompanyType = {
		id: number;
		name: string;
		label: string;
	};

	let {
		companies,
		companyTypes,
		selectedCompanies = $bindable([])
	}: {
		companies: Company[];
		companyTypes: CompanyType[];
		selectedCompanies: Company[];
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
					c.email.toLowerCase().includes(q) ||
					c.city.toLowerCase().includes(q)
			);
		}
		if (typeFilter) {
			result = result.filter((c) => c.company_type === typeFilter);
		}
		return result;
	});

	let selectedIds = $derived(new Set(selectedCompanies.map((c) => c.id)));

	function toggle(company: Company) {
		if (selectedIds.has(company.id)) {
			selectedCompanies = selectedCompanies.filter((c) => c.id !== company.id);
		} else {
			selectedCompanies = [...selectedCompanies, company];
		}
	}

	function toggleAll() {
		if (filtered.every((c) => selectedIds.has(c.id))) {
			const filteredIds = new Set(filtered.map((c) => c.id));
			selectedCompanies = selectedCompanies.filter((c) => !filteredIds.has(c.id));
		} else {
			const newSelections = filtered.filter((c) => !selectedIds.has(c.id));
			selectedCompanies = [...selectedCompanies, ...newSelections];
		}
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
		{selectedCompanies.length} selected / {filtered.length} shown
	</div>

	<div class="table-container">
		<table class="table">
			<thead>
				<tr>
					<th>
						<input
							type="checkbox"
							checked={filtered.length > 0 && filtered.every((c) => selectedIds.has(c.id))}
							onchange={toggleAll}
						/>
					</th>
					<th>Name</th>
					<th>Email</th>
					<th>Type</th>
					<th class="hidden lg:table-cell">City</th>
					<th class="hidden lg:table-cell">Domain</th>
				</tr>
			</thead>
			<tbody>
				{#each filtered as company (company.id)}
					<tr
						class="cursor-pointer hover:preset-tonal-primary"
						onclick={() => toggle(company)}
					>
						<td>
							<input
								type="checkbox"
								checked={selectedIds.has(company.id)}
								onclick={(e: MouseEvent) => e.stopPropagation()}
								onchange={() => toggle(company)}
							/>
						</td>
						<td>{company.name}</td>
						<td>{company.email || '—'}</td>
						<td>
							<span class="badge preset-filled-surface-500 text-xs">{company.company_type}</span>
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
