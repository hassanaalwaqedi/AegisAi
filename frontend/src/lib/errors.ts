export type AegisErrorCode =
  | "BACKEND_UNAVAILABLE"
  | "UNAUTHORIZED"
  | "INVALID_RESPONSE_SCHEMA"
  | "ENDPOINT_NOT_IMPLEMENTED"
  | "REQUEST_TIMEOUT"
  | "WEBSOCKET_DISCONNECTED"
  | "UNKNOWN_API_ERROR";

export class AegisClientError extends Error {
  code: AegisErrorCode;
  status?: number;
  details?: unknown;

  constructor(message: string, code: AegisErrorCode, status?: number, details?: unknown) {
    super(message);
    this.name = "AegisClientError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export function getErrorMessage(error: unknown) {
  if (error instanceof AegisClientError) return error.message;
  if (error instanceof Error) return error.message;
  return "An unknown frontend error occurred.";
}

export function getErrorCode(error: unknown) {
  if (error instanceof AegisClientError) return error.code;
  return "UNKNOWN_API_ERROR";
}
