const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

/** Generic JSON POST helper */
async function postJSON<T>(endpoint: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}

/** Multipart POST helper for file uploads */
async function postFormData<T>(endpoint: string, formData: FormData): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}

// ─── Request / Response types ────────────────────────────────────────

/** Payload for CSV or raw text supply chain data */
export interface SupplyChainTextPayload {
  format: 'csv' | 'text';
  content: string;
  fileName?: string;
}

/** Response after the backend processes text/csv data */
export interface SupplyChainTextResponse {
  success: boolean;
  message: string;
  jobId?: string;
}

/** Response after the backend processes an image upload */
export interface SupplyChainImageResponse {
  success: boolean;
  message: string;
  jobId?: string;
}

// ─── API calls ───────────────────────────────────────────────────────

/**
 * Upload CSV or raw text supply chain data.
 * The backend will parse/process this asynchronously.
 */
export async function uploadSupplyChainText(
  payload: SupplyChainTextPayload,
): Promise<SupplyChainTextResponse> {
  return postJSON<SupplyChainTextResponse>('/supply-chain/upload/text', payload);
}

/**
 * Upload an image (e.g. photo of a document, invoice, map).
 * The backend handles OCR / vision processing separately.
 */
export async function uploadSupplyChainImage(
  file: File,
): Promise<SupplyChainImageResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return postFormData<SupplyChainImageResponse>('/supply-chain/upload/image', formData);
}
