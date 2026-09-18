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
  if (error instanceof AegisClientError) {
    switch (error.code) {
      case "UNAUTHORIZED":
        return "Access is not configured correctly.";
      case "REQUEST_TIMEOUT":
        return "This request took too long. Try again.";
      case "WEBSOCKET_DISCONNECTED":
        return "Live updates are disconnected.";
      case "ENDPOINT_NOT_IMPLEMENTED":
        return "This information is not available in the current system setup.";
      case "INVALID_RESPONSE_SCHEMA":
        return "The latest information could not be read.";
      case "UNKNOWN_API_ERROR":
        return error.message.replace(/^Backend request failed with HTTP \d+:\s*/, "");
      case "BACKEND_UNAVAILABLE":
        return "This information is temporarily unavailable.";
    }
  }

  return "This information is temporarily unavailable.";
}

export function getErrorCode(error: unknown) {
  if (error instanceof AegisClientError) return error.code;
  return "UNKNOWN_API_ERROR";
}
