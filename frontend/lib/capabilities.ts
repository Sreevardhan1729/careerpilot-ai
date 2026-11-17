import { API_OPERATIONS } from "./api-capabilities.generated";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

const OPERATIONS = new Set(API_OPERATIONS);

function normalise(path: string): string {
  return path.replace(/\{[^}]*\}/g, "{}").replace(/\/+$/, "") || "/";
}

/**
 * True when the backend's OpenAPI document (captured by `pnpm gen:api`) exposes this operation.
 * FR-UI-02: an action whose backend is not built yet is not rendered.
 */
export function hasEndpoint(method: HttpMethod, path: string): boolean {
  return OPERATIONS.has(`${method} ${normalise(path)}`);
}

export function hasAllEndpoints(...ops: [HttpMethod, string][]): boolean {
  return ops.every(([m, p]) => hasEndpoint(m, p));
}
