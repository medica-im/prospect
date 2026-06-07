<script lang="ts">
	import CsvUploader from '$lib/twenty/CsvUploader.svelte';
	import ColumnMapper from '$lib/twenty/ColumnMapper.svelte';
	import ImportPreview from '$lib/twenty/ImportPreview.svelte';
	import ImportResults from '$lib/twenty/ImportResults.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let currentStep = $state(0);

	// State passed between steps
	let selectedCompanyTypeId = $state<number | null>(null);
	let uploadId = $state('');
	let csvHeaders = $state<string[]>([]);
	let rowCount = $state(0);
	let delimiter = $state(';');
	let transformerId = $state<number | null>(null);
	let previewRows = $state<any[]>([]);
	let totalDeduplicated = $state(0);
	let importResults = $state<any>(null);

	const stepLabels = ['Upload CSV', 'Map Columns', 'Preview', 'Import'];
</script>

<svelte:head>
	<title>Import Companies</title>
</svelte:head>

<h1 class="h3 mb-6">Import Companies to Twenty CRM</h1>

<!-- Step indicators -->
<div class="flex gap-2 mb-8">
	{#each stepLabels as label, i}
		<div class="flex items-center gap-2">
			<span
				class="badge-icon {i <= currentStep
					? 'preset-filled-primary-500'
					: 'preset-filled-surface-500'}"
			>
				{i + 1}
			</span>
			<span class="text-sm {i === currentStep ? 'font-bold' : 'text-surface-500'}">{label}</span>
			{#if i < stepLabels.length - 1}
				<span class="text-surface-400 mx-1">→</span>
			{/if}
		</div>
	{/each}
</div>

{#if currentStep === 0}
	<CsvUploader
		companyTypes={data.companyTypes}
		bind:selectedCompanyTypeId
		bind:delimiter
		onUploaded={(id, headers, count) => {
			uploadId = id;
			csvHeaders = headers;
			rowCount = count;
			currentStep = 1;
		}}
	/>
{:else if currentStep === 1}
	<ColumnMapper
		{csvHeaders}
		{delimiter}
		companyTypes={data.companyTypes}
		existingTransformers={data.transformers}
		{selectedCompanyTypeId}
		onMapped={(id) => {
			transformerId = id;
			currentStep = 2;
		}}
		onBack={() => (currentStep = 0)}
	/>
{:else if currentStep === 2}
	<ImportPreview
		{uploadId}
		{transformerId}
		bind:previewRows
		bind:totalDeduplicated
		onConfirm={() => (currentStep = 3)}
		onBack={() => (currentStep = 1)}
	/>
{:else if currentStep === 3}
	<ImportResults
		{uploadId}
		{transformerId}
		{selectedCompanyTypeId}
		{totalDeduplicated}
		bind:importResults
		onReset={() => {
			currentStep = 0;
			selectedCompanyTypeId = null;
			uploadId = '';
			csvHeaders = [];
			rowCount = 0;
			transformerId = null;
			previewRows = [];
			totalDeduplicated = 0;
			importResults = null;
		}}
	/>
{/if}
