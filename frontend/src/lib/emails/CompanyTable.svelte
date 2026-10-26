<script lang="ts">
	import {
		ArrowDownIcon,
		ArrowUpDownIcon,
		ArrowUpIcon,
		ExternalLinkIcon,
		MinusIcon,
		PlusIcon,
		SearchIcon,
		XIcon
	} from '@lucide/svelte';
	import {
		bulkRecipients as bulkOfRecipients,
		clampMaxSent,
		companyRecipients as recipientsOf,
		companyView,
		countByType,
		filterCompanies,
		headerCheckboxAction,
		lastSentTo as lastSentToIn,
		normalize,
		parseMaxSent,
		pruneOverLimit,
		recipientKey,
		selectModeSelection,
		sentTo as sentToIn,
		sortCompanies,
		stepMaxSent as nextMaxSent,
		updateExcluded,
		updateSelection,
		type AddressStats,
		type Company,
		type CompanyView,
		type Person,
		type SelectedRecipient,
		type SortField
	} from './selection';

	type CompanyType = {
		id: number;
		name: string;
		label: string;
	};

	let {
		companies,
		companyTypes,
		twentyBaseUrl = '',
		addressStats = {},
		unsubscribed = [],
		selectedRecipients = $bindable([])
	}: {
		companies: Company[];
		companyTypes: CompanyType[];
		twentyBaseUrl?: string;
		addressStats?: AddressStats;
		unsubscribed?: string[];
		selectedRecipients: SelectedRecipient[];
	} = $props();

	// Opted-out addresses stay fully visible — they are public data — but can
	// never be selected. The backend refuses them regardless.
	let unsubscribedSet = $derived(new Set(unsubscribed.map(normalize)));

	function isUnsubscribed(email: string): boolean {
		return unsubscribedSet.has(normalize(email));
	}

	function sentTo(email: string): number {
		return sentToIn(addressStats, email);
	}

	function lastSentTo(email: string): string | null {
		return lastSentToIn(addressStats, email);
	}

	// Upper bound on how many emails an address may already have received to be
	// shown and selected. null means no limit.
	let maxSent = $state<number | null>(null);

	function stepMaxSent(delta: 1 | -1) {
		maxSent = nextMaxSent(maxSent, delta);
		pruneOverMaxSent();
	}

	function typeMaxSent(e: Event & { currentTarget: HTMLInputElement }) {
		const { text, value } = parseMaxSent(e.currentTarget.value);
		if (e.currentTarget.value !== text) e.currentTarget.value = text;
		maxSent = clampMaxSent(value);
	}

	function maxSentKeys(e: KeyboardEvent) {
		if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
			e.preventDefault();
			stepMaxSent(e.key === 'ArrowUp' ? 1 : -1);
		}
	}

	// Committing a limit also trims a hand-made selection (select mode already
	// follows the limit). Done on change, not input: typing "12" would otherwise
	// prune at "1" first.
	function pruneOverMaxSent() {
		if (selectMode) return;
		selectedRecipients = pruneOverLimit(selectedRecipients, addressStats, maxSent);
	}

	function getHeatColor(dateStr: string | null | undefined): string {
		if (!dateStr) return 'text-surface-400';
		const now = Date.now();
		const sent = new Date(dateStr).getTime();
		const days = (now - sent) / (1000 * 60 * 60 * 24);
		if (days < 7) return 'text-green-600';
		if (days < 30) return 'text-yellow-600';
		if (days < 90) return 'text-orange-500';
		if (days < 180) return 'text-red-500';
		if (days < 365) return 'text-red-700 dark:text-red-400';
		return 'text-red-900 dark:text-red-300';
	}

	// Per-company results are computed once per data or limit change, not on
	// every render or sort comparison: the table has hundreds of rows.
	let viewById = $derived(
		new Map(companies.map((c) => [c.id, companyView(c, addressStats, maxSent)]))
	);
	let recipientsById = $derived(
		new Map(companies.map((c) => [c.id, recipientsOf(c, unsubscribedSet)]))
	);
	let bulkById = $derived(
		new Map(
			companies.map((c) => [c.id, bulkOfRecipients(companyRecipients(c), addressStats, maxSent)])
		)
	);

	const emptyView: CompanyView = {
		emails: [],
		people: [],
		hidden: 0,
		sent: 0,
		last: null,
		groupSent: 0,
		groupLastTime: 0
	};

	function viewOf(company: Company): CompanyView {
		return viewById.get(company.id) ?? emptyView;
	}

	function companyRecipients(company: Company): SelectedRecipient[] {
		return recipientsById.get(company.id) ?? [];
	}

	function bulkRecipients(company: Company): SelectedRecipient[] {
		return bulkById.get(company.id) ?? [];
	}

	// Intl formatters are costly to build; toLocaleDateString builds one per call.
	const dateFormat = new Intl.DateTimeFormat('fr-FR', {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric'
	});
	const dateTimeFormat = new Intl.DateTimeFormat('fr-FR', {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit'
	});

	function formatDate(value: string): string {
		return dateFormat.format(new Date(value));
	}

	function formatDateTime(value: string): string {
		return dateTimeFormat.format(new Date(value));
	}

	let search = $state('');
	let typeFilter = $state('');
	let noEmailOnly = $state(false);

	let sortField = $state<SortField>('created_at');
	let sortDesc = $state(true);

	function toggleSort(field: SortField) {
		if (sortField === field) {
			sortDesc = !sortDesc;
		} else {
			sortField = field;
			sortDesc = true;
		}
	}

	// Every filter but the type, so each type button can say what it would show.
	let preType = $derived(filterCompanies(companies, { search, noEmailOnly, maxSent }, bulkRecipients));

	let typeCounts = $derived(countByType(preType));

	let filtersActive = $derived(!!search || !!typeFilter || noEmailOnly || maxSent !== null);

	function resetFilters() {
		search = '';
		typeFilter = '';
		noEmailOnly = false;
		maxSent = null;
	}

	let filtered = $derived(
		sortCompanies(
			typeFilter ? preType.filter((c) => c.company_type === typeFilter) : preType,
			sortField,
			sortDesc,
			viewOf
		)
	);

	let selectedKeys = $derived(new Set(selectedRecipients.map(recipientKey)));

	// How many of the currently visible addresses are opted out.
	let unsubscribedShown = $derived.by(() => {
		if (unsubscribedSet.size === 0) return 0;
		const seen = new Set<string>();
		for (const company of filtered) {
			for (const email of company.emails) {
				if (isUnsubscribed(email)) seen.add(normalize(email));
			}
			for (const person of company.people ?? []) {
				if (person.email && isUnsubscribed(person.email)) seen.add(normalize(person.email));
			}
		}
		return seen.size;
	});

	// Addresses of the listed companies that the sent limit hides.
	let hiddenByLimit = $derived(filtered.reduce((n, c) => n + viewOf(c).hidden, 0));

	let allFilteredSelected = $derived.by(() => {
		const keys = filtered.flatMap((c) => bulkRecipients(c).map(recipientKey));
		return keys.length > 0 && keys.every((k) => selectedKeys.has(k));
	});

	// Select mode, entered from the header checkbox: the selection is computed
	// from the filters (search, type, sent limit) instead of being a fixed list,
	// so changing a filter re-selects. Boxes unticked by hand meanwhile are
	// remembered as exceptions and survive filter changes.
	let selectMode = $state(false);
	let excluded = $state(new Set<string>());

	$effect(() => {
		if (selectMode) {
			selectedRecipients = selectModeSelection(filtered, bulkRecipients, excluded);
		}
	});

	// Eligible visible addresses unticked by hand while in select mode.
	let excludedShown = $derived.by(() => {
		if (!selectMode) return 0;
		return filtered.reduce(
			(n, c) => n + bulkRecipients(c).filter((r) => excluded.has(recipientKey(r))).length,
			0
		);
	});

	function setPicked(recips: SelectedRecipient[], pick: boolean) {
		if (selectMode) excluded = updateExcluded(excluded, recips, pick);
		else selectedRecipients = updateSelection(selectedRecipients, recips, pick);
	}

	function toggleEmail(company: Company, email: string) {
		if (isUnsubscribed(email)) return;
		const r = {
			company_id: company.id,
			company_name: company.name,
			company_email: email,
			company_type: company.company_type
		};
		setPicked([r], !selectedKeys.has(recipientKey(r)));
	}

	function togglePerson(company: Company, person: Person) {
		if (isUnsubscribed(person.email)) return;
		const r = {
			company_id: person.id,
			company_name: company.name,
			company_email: person.email,
			company_type: company.company_type
		};
		setPicked([r], !selectedKeys.has(recipientKey(r)));
	}

	function toggleCompany(company: Company) {
		const recips = bulkRecipients(company);
		if (recips.length === 0) return;
		setPicked(recips, !recips.every((r) => selectedKeys.has(recipientKey(r))));
	}

	// Leave select mode keeping the current selection as a fixed list.
	function freezeSelection() {
		selectMode = false;
		excluded = new Set();
	}

	export function clearSelection() {
		freezeSelection();
		selectedRecipients = [];
	}

	function toggleAll() {
		const action = headerCheckboxAction(selectMode, allFilteredSelected);
		if (action === 'clear') {
			clearSelection();
		} else if (action === 'untick-shown') {
			setPicked(filtered.flatMap(bulkRecipients), false);
		} else {
			excluded = new Set();
			selectMode = true;
		}
	}

	function isCompanyFullySelected(company: Company) {
		const keys = bulkRecipients(company).map(recipientKey);
		return keys.length > 0 && keys.every((k) => selectedKeys.has(k));
	}

	function isCompanyPartiallySelected(company: Company) {
		const keys = bulkRecipients(company).map(recipientKey);
		return keys.some((k) => selectedKeys.has(k)) && !isCompanyFullySelected(company);
	}
</script>

{#snippet sentBadge(email: string)}
	{@const n = sentTo(email)}
	{#if n > 0}
		<span
			class="text-xs whitespace-nowrap text-surface-500 tabular-nums"
			title="{n} email(s) already sent to this address"
		>
			×{n}
		</span>
	{/if}
{/snippet}

{#snippet filterLabel(text: string)}
	<span class="text-xs font-semibold tracking-wide text-surface-600-400 uppercase">{text}</span>
{/snippet}

{#snippet sortHeader(field: 'created_at' | 'last_sent' | 'sent_count', label: string)}
	{@const active = sortField === field}
	<button
		type="button"
		class="inline-flex items-center gap-1 whitespace-nowrap transition-colors {active
			? 'text-primary-600-400'
			: 'hover:text-surface-950-50'}"
		title="Sort by {label.toLowerCase()}"
		onclick={() => toggleSort(field)}
	>
		{label}
		{#if !active}
			<ArrowUpDownIcon class="size-3.5 opacity-50" />
		{:else if sortDesc}
			<ArrowDownIcon class="size-3.5" />
		{:else}
			<ArrowUpIcon class="size-3.5" />
		{/if}
	</button>
{/snippet}

<div class="space-y-4">
	<div
		class="card flex flex-wrap items-end gap-x-6 gap-y-4 preset-outlined-surface-200-800 p-4"
	>
		<label class="flex w-full flex-col gap-1.5 sm:w-64">
			{@render filterLabel('Search')}
			<span class="relative">
				<SearchIcon
					class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-surface-500"
				/>
				<input
					type="search"
					placeholder="Name, email, city…"
					class="input pl-8"
					bind:value={search}
				/>
			</span>
		</label>

		<div class="flex flex-col gap-1.5">
			{@render filterLabel('Type')}
			<div class="flex flex-wrap gap-1" role="group" aria-label="Company type">
				{#each [{ name: '', label: 'All' }, ...companyTypes] as ct (ct.name)}
					{@const count = ct.name ? (typeCounts.get(ct.name) ?? 0) : preType.length}
					<button
						type="button"
						class="btn btn-sm {typeFilter === ct.name
							? 'preset-filled-primary-500'
							: 'preset-tonal-surface'} {count === 0 && typeFilter !== ct.name
							? 'opacity-50'
							: ''}"
						aria-pressed={typeFilter === ct.name}
						onclick={() => (typeFilter = ct.name)}
					>
						{ct.label}
						<span class="text-xs tabular-nums opacity-70">{count}</span>
					</button>
				{/each}
			</div>
		</div>

		<div class="flex flex-col gap-1.5">
			{@render filterLabel('Emails received')}
			<div class="flex items-center gap-2">
				<div
					class="flex items-stretch overflow-hidden rounded-base border border-surface-300-700 focus-within:ring-2 focus-within:ring-primary-500"
					title="Bulk selection only picks addresses that already received this many emails or fewer. ↑/↓ step it."
				>
					<button
						type="button"
						class="px-2 hover:preset-tonal-surface disabled:opacity-40"
						aria-label="Fewer"
						disabled={maxSent === null}
						onclick={() => stepMaxSent(-1)}
					>
						<MinusIcon class="size-4" />
					</button>
					<span class="flex items-center border-x border-surface-300-700 pl-2 text-surface-500">≤</span>
					<input
						type="text"
						inputmode="numeric"
						maxlength="3"
						placeholder="Any"
						aria-label="Maximum emails already received"
						class="w-12 border-0 bg-transparent px-1 py-1 text-center tabular-nums focus:ring-0"
						value={maxSent ?? ''}
						oninput={typeMaxSent}
						onchange={pruneOverMaxSent}
						onkeydown={maxSentKeys}
					/>
					<button
						type="button"
						class="border-l border-surface-300-700 px-2 hover:preset-tonal-surface disabled:opacity-40"
						aria-label="More"
						disabled={maxSent === 999}
						onclick={() => stepMaxSent(1)}
					>
						<PlusIcon class="size-4" />
					</button>
				</div>
				<span class="w-24 text-xs text-surface-600-400">
					{maxSent === null ? 'no limit' : maxSent === 0 ? 'never emailed' : 'or fewer'}
				</span>
			</div>
		</div>

		<div class="flex flex-col gap-1.5">
			{@render filterLabel('Show')}
			<button
				type="button"
				class="btn btn-sm {noEmailOnly ? 'preset-filled-primary-500' : 'preset-tonal-surface'}"
				aria-pressed={noEmailOnly}
				onclick={() => (noEmailOnly = !noEmailOnly)}
			>
				Without email only
			</button>
		</div>

		{#if filtersActive}
			<button
				type="button"
				class="btn btn-sm ml-auto preset-tonal-surface"
				onclick={resetFilters}
			>
				<XIcon class="size-4" /> Reset
			</button>
		{/if}
	</div>

	<div class="flex flex-wrap items-center gap-2 text-sm text-surface-600-400">
		<span>
			<strong class="text-surface-950-50 tabular-nums">{selectedRecipients.length}</strong>
			email(s) selected ·
			<span class="tabular-nums">{filtered.length}</span> companies shown
		</span>
		{#if unsubscribedShown > 0}
			<span class="badge preset-tonal-error text-xs">
				{unsubscribedShown} désabonné(s) exclu(s)
			</span>
		{/if}
		{#if hiddenByLimit > 0}
			<span class="badge preset-tonal-warning text-xs">
				{hiddenByLimit} address(es) hidden: already received more than {maxSent}
			</span>
		{/if}
	</div>

	{#if selectMode}
		<div
			class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-container preset-tonal-primary px-3 py-2 text-sm"
		>
			<span>
				<strong>Select mode</strong> — the selection follows the search, type and sent filters.
				{#if excludedShown > 0}
					{excludedShown} unticked by hand.
				{/if}
			</span>
			<span class="ml-auto flex gap-2">
				<button
					type="button"
					class="btn btn-sm preset-outlined-surface-500"
					title="Keep the current selection as it is and stop following the filters"
					onclick={freezeSelection}
				>
					Freeze selection
				</button>
				<button type="button" class="btn btn-sm preset-outlined-surface-500" onclick={clearSelection}>
					Clear
				</button>
			</span>
		</div>
	{/if}

	<div class="table-container">
		<table class="table">
			<thead>
				<tr class="text-xs tracking-wide text-surface-600-400 uppercase">
					<th class="w-10">
						<input
							type="checkbox"
							class="checkbox"
							checked={selectMode || allFilteredSelected}
							indeterminate={selectMode && excludedShown > 0}
							aria-label="Select everything matching the filters"
							title={selectMode
								? 'Clear the selection'
								: 'Select everything matching the filters, and keep following them'}
							onchange={toggleAll}
						/>
					</th>
					<th class="min-w-64">Name</th>
					<th>Emails</th>
					<th>Type</th>
					<th class="hidden md:table-cell">{@render sortHeader('sent_count', 'Sent')}</th>
					<th class="hidden md:table-cell">{@render sortHeader('last_sent', 'Last email')}</th>
					<th class="hidden lg:table-cell">City</th>
					<th class="hidden lg:table-cell">Domain</th>
					<th class="hidden lg:table-cell">{@render sortHeader('created_at', 'Added')}</th>
					{#if twentyBaseUrl}
						<th class="hidden lg:table-cell">CRM</th>
					{/if}
				</tr>
			</thead>
			<tbody>
				{#each filtered as company (company.id)}
					{@const view = viewOf(company)}
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
						<td class="min-w-64 font-medium">{company.name}</td>
						<td onclick={(e: MouseEvent) => e.stopPropagation()}>
							{#if view.emails.length === 0}
								<span class="text-surface-400">
									{company.emails.length > 0
										? `${company.emails.length} hidden by the limit`
										: '—'}
								</span>
							{:else}
								<div class="flex flex-col gap-1">
									{#each view.emails as email}
										<label class="flex items-center gap-2">
											<input
												type="checkbox"
												checked={selectedKeys.has(`${company.id}:${email}`)}
												disabled={isUnsubscribed(email)}
												onchange={() => toggleEmail(company, email)}
											/>
											<span class={isUnsubscribed(email) ? 'text-surface-400 line-through' : ''}>
												{email}
											</span>
											{@render sentBadge(email)}
											{#if isUnsubscribed(email)}
												<span class="badge preset-filled-error-500 text-xs whitespace-nowrap">
													Désabonné
												</span>
											{/if}
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
						<td class="hidden md:table-cell text-center tabular-nums">
							{#if view.emails.length > 0}
								{view.sent}
							{:else}
								<span class="text-surface-400">—</span>
							{/if}
						</td>
						<td class="hidden md:table-cell whitespace-nowrap text-sm font-medium {getHeatColor(view.last)}">
							{#if view.last}
								{formatDate(view.last)}
							{:else}
								<span class="text-surface-400">—</span>
							{/if}
						</td>
						<td class="hidden lg:table-cell">{company.city || '—'}</td>
						<td class="hidden lg:table-cell">
							{#if company.domain}
								<a
									href={/^https?:\/\//.test(company.domain)
										? company.domain
										: `https://${company.domain}`}
									target="_blank"
									rel="noopener"
									class="anchor"
									onclick={(e: MouseEvent) => e.stopPropagation()}
								>
									<!-- Twenty v2 stores domains without the scheme; v1 kept it. -->
									{company.domain.replace(/^https?:\/\//, '')}
								</a>
							{:else}
								—
							{/if}
						</td>
						<td class="hidden lg:table-cell text-sm text-surface-600-400 whitespace-nowrap">
							{formatDateTime(company.created_at)}
						</td>
						{#if twentyBaseUrl}
							<td class="hidden lg:table-cell">
								<a
									href="{twentyBaseUrl}/object/company/{company.id}"
									target="_blank"
									rel="noopener"
									class="text-surface-500 hover:text-surface-950-50 transition-colors"
									title="Open in Twenty CRM"
									onclick={(e: MouseEvent) => e.stopPropagation()}
								>
									<ExternalLinkIcon class="size-4" />
								</a>
							</td>
						{/if}
					</tr>
					{#each view.people as person, pi (person.id)}
						{@const personLast = lastSentTo(person.email)}
						<tr
							class="cursor-pointer hover:preset-tonal-primary text-sm"
							onclick={() => togglePerson(company, person)}
						>
							<td></td>
							<td class="min-w-64">
								<span class="text-surface-400 font-mono mr-1">
									{pi === view.people.length - 1 ? '└─' : '├─'}
								</span>
								{person.name || '—'}
							</td>
							<td onclick={(e: MouseEvent) => e.stopPropagation()}>
								<label class="flex items-center gap-2">
									<input
										type="checkbox"
										checked={selectedKeys.has(`${person.id}:${person.email}`)}
										disabled={isUnsubscribed(person.email)}
										onchange={() => togglePerson(company, person)}
									/>
									<span class={isUnsubscribed(person.email) ? 'text-surface-400 line-through' : ''}>
										{person.email}
									</span>
									{#if isUnsubscribed(person.email)}
										<span class="badge preset-filled-error-500 text-xs whitespace-nowrap">
											Désabonné
										</span>
									{/if}
								</label>
							</td>
							<td>
								<span class="badge preset-filled-tertiary-500 text-xs">People</span>
							</td>
							<td class="hidden md:table-cell text-center tabular-nums">
								{sentTo(person.email)}
							</td>
							<td class="hidden md:table-cell whitespace-nowrap text-sm font-medium {getHeatColor(personLast)}">
								{#if personLast}
									{formatDate(personLast)}
								{:else}
									<span class="text-surface-400">—</span>
								{/if}
							</td>
							<td class="hidden lg:table-cell text-surface-400">—</td>
							<td class="hidden lg:table-cell text-surface-400">—</td>
							<td class="hidden lg:table-cell text-sm text-surface-600-400 whitespace-nowrap">
								{#if person.created_at}
									{formatDateTime(person.created_at)}
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
										class="text-surface-500 hover:text-surface-950-50 transition-colors"
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
