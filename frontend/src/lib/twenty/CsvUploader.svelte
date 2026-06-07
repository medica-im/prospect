<script lang="ts">
	type CompanyType = {
		id: number;
		name: string;
		label: string;
	};

	let {
		companyTypes,
		selectedCompanyTypeId = $bindable(null),
		delimiter = $bindable(';'),
		onUploaded
	}: {
		companyTypes: CompanyType[];
		selectedCompanyTypeId: number | null;
		delimiter: string;
		onUploaded: (uploadId: string, headers: string[], rowCount: number) => void;
	} = $props();

	let fileInput = $state<HTMLInputElement | null>(null);
	let hasFile = $state(false);
	let uploading = $state(false);
	let error = $state('');

	async function handleUpload() {
		if (!selectedCompanyTypeId || !fileInput?.files?.[0]) return;
		uploading = true;
		error = '';

		const formData = new FormData();
		formData.append('file', fileInput.files[0]);
		formData.append('delimiter', delimiter);

		try {
			const response = await fetch('/twenty/import/api/upload-csv', {
				method: 'POST',
				body: formData
			});
			const json = await response.json();
			if (response.ok && json.upload_id) {
				onUploaded(json.upload_id, json.headers, json.row_count);
			} else {
				error = json.detail || 'Upload failed';
			}
		} catch (e) {
			error = String(e);
		} finally {
			uploading = false;
		}
	}
</script>

<div class="card p-6 space-y-4">
	<label class="label">
		<span class="font-bold">Company Type</span>
		<select class="select" bind:value={selectedCompanyTypeId}>
			<option value={null}>Select a type...</option>
			{#each companyTypes as ct}
				<option value={ct.id}>{ct.label}</option>
			{/each}
		</select>
	</label>

	<label class="label">
		<span class="font-bold">CSV Delimiter</span>
		<select class="select w-32" bind:value={delimiter}>
			<option value=";">Semicolon (;)</option>
			<option value=",">Comma (,)</option>
			<option value="\t">Tab</option>
		</select>
	</label>

	<label class="label">
		<span class="font-bold">CSV File</span>
		<input type="file" accept=".csv,.txt" class="input" bind:this={fileInput}
			onchange={() => (hasFile = !!fileInput?.files?.length)} />
	</label>

	{#if error}
		<aside class="alert preset-filled-error-500">
			<p>{error}</p>
		</aside>
	{/if}

	<button
		class="btn preset-filled-primary-500"
		disabled={!selectedCompanyTypeId || uploading || !hasFile}
		onclick={handleUpload}
	>
		{uploading ? 'Uploading...' : 'Upload and Continue →'}
	</button>
</div>
