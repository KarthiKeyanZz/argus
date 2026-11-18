/**
 * Typed API client. `schema.d.ts` is generated from the backend's OpenAPI document
 * (`npm run gen:api`), so every path, parameter and response here is type-checked
 * against the real API.
 */
import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export const api = createClient<paths>({ baseUrl: "" });

/** Error thrown for any non-2xx response, carrying the backend's error envelope. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(message: string, status: number, code: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface Envelope {
  error?: { code?: string; message?: string; details?: Record<string, unknown> };
  detail?: Array<{ loc?: unknown[]; msg?: string }> | string;
}

export function toApiError(body: unknown, status: number): ApiError {
  const env = (body ?? {}) as Envelope;
  if (env.error?.message) {
    return new ApiError(env.error.message, status, env.error.code ?? "error", env.error.details);
  }
  // FastAPI request-validation errors: {"detail": [{"loc": [...], "msg": "..."}]}
  if (Array.isArray(env.detail) && env.detail.length > 0) {
    const first = env.detail[0];
    const field = Array.isArray(first?.loc) ? first.loc.slice(1).join(".") : "";
    return new ApiError(`${field ? `${field}: ` : ""}${first?.msg ?? "Invalid input"}`, status, "validation_error");
  }
  return new ApiError(`Request failed (${status})`, status, "http_error");
}

/** Await an openapi-fetch call and return its data, or throw an ApiError. */
export async function unwrap<T>(call: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok || error !== undefined) {
    throw toApiError(error, response.status);
  }
  return data as T;
}

/** Multipart upload (openapi-fetch is JSON-first, so use fetch directly). */
export async function uploadResume(file: File): Promise<Schemas["ResumeUploadResult"]> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/v1/resumes", { method: "POST", body: form });
  const body: unknown = await response.json().catch(() => ({}));
  if (!response.ok) throw toApiError(body, response.status);
  return body as Schemas["ResumeUploadResult"];
}
