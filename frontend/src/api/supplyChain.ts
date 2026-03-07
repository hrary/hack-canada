import type { AnalysisResult, SimulationScenario, SimulationResult, SupplierResearch, RiskFactor, Alternative } from '../types';

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

/** Generic JSON GET helper */
async function getJSON<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${endpoint}`);
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

// ─── Analysis API ────────────────────────────────────────────────────

/**
 * Kick off the full analysis pipeline for a previously uploaded job.
 */
export async function runAnalysis(jobId: string): Promise<AnalysisResult> {
  return postJSON<AnalysisResult>(`/analysis/run/${encodeURIComponent(jobId)}`, {});
}

/**
 * Poll / fetch analysis results for a job.
 */
export async function getAnalysisResult(jobId: string): Promise<AnalysisResult> {
  return getJSON<AnalysisResult>(`/analysis/result/${encodeURIComponent(jobId)}`);
}

// ─── Simulation API ──────────────────────────────────────────────────

/**
 * Run one or more what-if scenarios against an existing supply chain.
 */
export async function runSimulation(
  jobId: string,
  scenarios: SimulationScenario[],
): Promise<SimulationResult[]> {
  return postJSON<SimulationResult[]>('/simulation/run', {
    job_id: jobId,
    scenarios,
  });
}

// ─── Streaming Analysis (SSE) ────────────────────────────────────────

export interface AnalysisSSECallbacks {
  onResearch?: (data: { job_id: string; supplier_research: SupplierResearch[] }) => void;
  onRisk?: (data: { job_id: string; risks: RiskFactor[]; alternatives: Alternative[]; summary: string }) => void;
  onDone?: (result: AnalysisResult) => void;
  onStatus?: (data: { phase: string; message: string }) => void;
  onError?: (err: Error) => void;
}

/**
 * Connect to the SSE analysis stream and invoke callbacks as each phase
 * completes. Returns an AbortController the caller can use to cancel.
 */
export function streamAnalysis(
  jobId: string,
  callbacks: AnalysisSSECallbacks,
): AbortController {
  const controller = new AbortController();
  const url = `${API_BASE_URL}/analysis/stream/${encodeURIComponent(jobId)}`;

  (async () => {
    try {
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) {
        const err = await res.text();
        callbacks.onError?.(new Error(`SSE error ${res.status}: ${err}`));
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Process complete events (terminated by \n\n)
        const parts = buffer.split('\n\n');
        buffer = parts.pop()!; // last part is incomplete or empty

        for (const part of parts) {
          if (!part.trim()) continue;
          let eventType = 'message';
          let data = '';
          for (const line of part.split('\n')) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim();
            else if (line.startsWith('data: ')) data = line.slice(6);
          }
          if (!data) continue;

          try {
            const parsed = JSON.parse(data);
            switch (eventType) {
              case 'status':
                callbacks.onStatus?.(parsed);
                break;
              case 'research':
                callbacks.onResearch?.(parsed);
                break;
              case 'risk':
                callbacks.onRisk?.(parsed);
                break;
              case 'done':
                callbacks.onDone?.(parsed);
                break;
            }
          } catch {
            // skip malformed JSON
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        callbacks.onError?.(err as Error);
      }
    }
  })();

  return controller;
}
