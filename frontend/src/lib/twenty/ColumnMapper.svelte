<script lang="ts">
	type CompanyType = {
		id: number;
		name: string;
		label: string;
	};

	type Transformer = {
		id: number;
		name: string;
		company_type_id: number;
		csv_name_column: string;
		csv_email_column: string;
		csv_postcode_column: string;
		csv_domain_column: string;
		csv_delimiter: string;
	};

	let {
		csvHeaders,
		delimiter,
		companyTypes,
		existingTransformers,
		selectedCompanyTypeId,
		onMapped,
		onBack
	}: {
		csvHeaders: string[];
		delimiter: string;
		companyTypes: CompanyType[];
		existingTransformers: Transformer[];
		selectedCompanyTypeId: number | null;
		onMapped: (transformerId: number) => void;
		onBack: () => void;
	} = $props();

	// Column mapping state
	let nameColumn = $state('');
	let emailColumn = $state('');
	let postcodeColumn = $state('');
	let domainColumn = $state('');
	let transformerName = $state('');
	let selectedTransformerId = $state<number | null>(null);

	let saving = $state(false);
	let error = $state('');

	// Filter existing transformers by selected company type
	let matchingTransformers = $derived(
		existingTransformers.filter((t) => t.company_type_id === selectedCompanyTypeId)
	);

	function loadTransformer(transformer: Transformer) {
		nameColumn = transformer.csv_name_column;
		emailColumn = transformer.csv_email_column;
		postcodeColumn = transformer.csv_postcode_column;
		domainColumn = transformer.csv_domain_column;
		selectedTransformerId = transformer.id;
		transformerName = transformer.name;
	}

	let canProceed = $derived(nameColumn && emailColumn && postcodeColumn);

	async function handleSaveAndContinue() {
		if (!canProceed || !selectedCompanyTypeId) return;

		// If using an existing transformer with matching columns, skip creation
		if (selectedTransformerId) {
			const existing = existingTransformers.find((t) => t.id === selectedTransformerId);
			if (
				existing &&
				existing.csv_name_column === nameColumn &&
				existing.csv_email_column === emailColumn &&
				existing.csv_postcode_column === postcodeColumn &&
				existing.csv_domain_column === domainColumn
			) {
				onMapped(selectedTransformerId);
				return;
			}
		}

		// Create new transformer
		if (!transformerName.trim()) {
			error = 'Please enter a name for this column mapping.';
			return;
		}

		saving = true;
		error = '';

		try {
			const response = await fetch('/twenty/import/api/transformers', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					name: transformerName,
					company_type_id: selectedCompanyTypeId,
					csv_name_column: nameColumn,
					csv_email_column: emailColumn,
					csv_postcode_column: postcodeColumn,
					csv_domain_column: domainColumn,
					csv_delimiter: delimiter
				})
			});

			const json = await response.json();
			if (response.ok) {
				onMapped(json.id);
			} else {
				error = json.detail || JSON.stringify(json);
			}
		} catch (e) {
			error = String(e);
		} finally {
			saving = false;
		}
	}
</script>

<div class="space-y-6">
	{#if matchingTransformers.length > 0}
		<div class="card p-4 space-y-2">
			<h3 class="font-bold">Existing column mappings</h3>
			<div class="flex flex-wrap gap-2">
				{#each matchingTransformers as t}
					<button
						class="btn {selectedTransformerId === t.id
							? 'preset-filled-primary-500'
							: 'preset-outlined-surface-500'}"
						onclick={() => loadTransformer(t)}
					>
						{t.name}
					</button>
				{/each}
			</div>
		</div>
	{/if}

	<div class="card p-6 space-y-4">
		<h3 class="font-bold">Map CSV columns to Twenty CRM fields</h3>

		<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
			<label class="label">
				<span>Company Name *</span>
				<select class="select" bind:value={nameColumn}>
					<option value="">Select column...</option>
					{#each csvHeaders as h}
						<option value={h}>{h}</option>
					{/each}
				</select>
			</label>

			<label class="label">
				<span>Email *</span>
				<select class="select" bind:value={emailColumn}>
					<option value="">Select column...</option>
					{#each csvHeaders as h}
						<option value={h}>{h}</option>
					{/each}
				</select>
			</label>

			<label class="label">
				<span>Postal Code (Code département) *</span>
				<select class="select" bind:value={postcodeColumn}>
					<option value="">Select column...</option>
					{#each csvHeaders as h}
						<option value={h}>{h}</option>
					{/each}
				</select>
			</label>

			<label class="label">
				<span>Domain (optional)</span>
				<select class="select" bind:value={domainColumn}>
					<option value="">None</option>
					{#each csvHeaders as h}
						<option value={h}>{h}</option>
					{/each}
				</select>
			</label>
		</div>

		{#if !selectedTransformerId}
			<label class="label">
				<span>Save this mapping as</span>
				<input
					type="text"
					class="input"
					placeholder="e.g. CPTS CSV 2024"
					bind:value={transformerName}
				/>
			</label>
		{/if}
	</div>

	{#if error}
		<aside class="alert preset-filled-error-500">
			<p>{error}</p>
		</aside>
	{/if}

	<div class="flex justify-between">
		<button class="btn preset-outlined-surface-500" onclick={onBack}>← Back</button>
		<button
			class="btn preset-filled-primary-500"
			disabled={!canProceed || saving}
			onclick={handleSaveAndContinue}
		>
			{saving ? 'Saving...' : 'Preview →'}
		</button>
	</div>
</div>
