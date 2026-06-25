const API_BASE = import.meta.env.VITE_API_URL || '/api';

function getAuthHeader() {
  const username = import.meta.env.VITE_ADMIN_USERNAME || 'admin';
  const password = import.meta.env.VITE_ADMIN_PASSWORD || 'changeme';
  return 'Basic ' + btoa(`${username}:${password}`);
}

function parseErrorBody(err) {
  if (!err) return 'Request failed';
  if (typeof err.detail === 'string') return err.detail;
  if (Array.isArray(err.detail)) {
    return err.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  }
  return JSON.stringify(err);
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Authorization: getAuthHeader(),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(parseErrorBody(err));
  }

  return response.json();
}

export async function checkHealth() {
  return request('/health');
}

export async function listCalls() {
  return request('/calls');
}

export async function uploadAudioFiles(files) {
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }
  return request('/upload', { method: 'POST', body: formData });
}

export async function runComparison({ fileId, callReference }) {
  return request('/run-comparison', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      file_id: fileId,
      call_reference: callReference || null,
    }),
  });
}

export async function getResults(jobId) {
  return request(`/results/${jobId}`);
}

export async function retryFailedProviders(jobId, solutionIds = null) {
  return request(`/results/${jobId}/retry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ solution_ids: solutionIds }),
  });
}

export async function downloadWordReport(jobId) {
  const response = await fetch(`${API_BASE}/results/${jobId}/export/docx`, {
    headers: { Authorization: getAuthHeader() },
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(parseErrorBody(err));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `comparison-${jobId}.docx`;
  a.click();
  URL.revokeObjectURL(url);
}

/** @deprecated Use downloadWordReport */
export async function downloadExport(jobId, format = 'docx') {
  if (format !== 'docx') {
    throw new Error('Only Word (.docx) export is available.');
  }
  return downloadWordReport(jobId);
}
