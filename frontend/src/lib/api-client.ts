import { z } from "zod";
import { appConfig } from "@/lib/config";
import { AegisClientError } from "@/lib/errors";
import {
  browserFrameResponseSchema,
  cameraOverlayResponseSchema,
  cameraConnectionTestResponseSchema,
  cameraDetectionsResponseSchema,
  cameraEventsResponseSchema,
  cameraSchema,
  camerasResponseSchema,
  eventsResponseSchema,
  semanticQueryRequestSchema,
  semanticQueryResponseSchema,
  semanticResultsResponseSchema,
  statisticsResponseSchema,
  statusResponseSchema,
  tracksResponseSchema,
  videoUploadResponseSchema
} from "@/lib/schemas";
import type { CameraSourceType } from "@/types";

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  timeoutMs?: number;
};

type CameraCreateInput = {
  camera_id: string;
  source_type: CameraSourceType;
  name?: string;
  location?: string;
  enabled?: boolean;
  url?: string;
  device_index?: number;
  auto_start?: boolean;
  connection_timeout?: number;
  max_retries?: number;
  metadata?: Record<string, unknown>;
};

export type CameraUpdateInput = Partial<
  Pick<
    CameraCreateInput,
    "name" | "location" | "enabled" | "url" | "device_index" | "connection_timeout" | "max_retries" | "metadata"
  >
>;

function buildHeaders(includeJson = true) {
  const headers: Record<string, string> = {
    Accept: "application/json"
  };

  if (includeJson) headers["Content-Type"] = "application/json";

  return headers;
}

async function parseJson(response: Response) {
  try {
    return await response.json();
  } catch {
    throw new AegisClientError("Backend returned a non-JSON response.", "INVALID_RESPONSE_SCHEMA", response.status);
  }
}

class AegisApiClient {
  private async request<TSchema extends z.ZodTypeAny>(
    path: string,
    schema: TSchema,
    options: RequestOptions = {}
  ): Promise<z.infer<TSchema>> {
    const controller = new AbortController();
    const timeout = window.setTimeout(
      () => controller.abort(),
      options.timeoutMs ?? appConfig.requestTimeoutMs
    );

    try {
      const response = await fetch(`${appConfig.apiUrl}${path}`, {
        method: options.method ?? "GET",
        headers: buildHeaders(),
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
        cache: "no-store"
      });

      if (response.status === 401 || response.status === 403) {
        throw new AegisClientError(
          "Unauthorized request. Check public dashboard auth configuration or backend session authentication.",
          "UNAUTHORIZED",
          response.status
        );
      }

      if (response.status === 404 || response.status === 405 || response.status === 501) {
        throw new AegisClientError(
          `Endpoint ${path} is not implemented by the backend.`,
          "ENDPOINT_NOT_IMPLEMENTED",
          response.status
        );
      }

      if (!response.ok) {
        let detail = "";
        try {
          const json = await response.json();
          detail = typeof json.detail === "string" ? json.detail : JSON.stringify(json.detail ?? json);
        } catch {
          detail = "";
        }

        throw new AegisClientError(
          detail ? `Backend request failed with HTTP ${response.status}: ${detail}` : `Backend request failed with HTTP ${response.status}.`,
          "UNKNOWN_API_ERROR",
          response.status
        );
      }

      const json = await parseJson(response);
      const parsed = schema.safeParse(json);

      if (!parsed.success) {
        throw new AegisClientError(
          `Invalid response schema from ${path}.`,
          "INVALID_RESPONSE_SCHEMA",
          response.status,
          parsed.error.flatten()
        );
      }

      return parsed.data;
    } catch (error) {
      if (error instanceof AegisClientError) throw error;

      if (error instanceof DOMException && error.name === "AbortError") {
        throw new AegisClientError(`Request to ${path} timed out.`, "REQUEST_TIMEOUT");
      }

      throw new AegisClientError(
        `Backend unavailable at ${appConfig.apiUrl}.`,
        "BACKEND_UNAVAILABLE",
        undefined,
        error
      );
    } finally {
      window.clearTimeout(timeout);
    }
  }

  private async upload<TSchema extends z.ZodTypeAny>(
    path: string,
    schema: TSchema,
    formData: FormData,
    timeoutMs = 120000
  ): Promise<z.infer<TSchema>> {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(`${appConfig.apiUrl}${path}`, {
        method: "POST",
        headers: buildHeaders(false),
        body: formData,
        signal: controller.signal,
        cache: "no-store"
      });

      if (response.status === 401 || response.status === 403) {
        throw new AegisClientError(
          "Unauthorized request. Check public dashboard auth configuration or backend session authentication.",
          "UNAUTHORIZED",
          response.status
        );
      }

      if (response.status === 404 || response.status === 405 || response.status === 501) {
        throw new AegisClientError(
          `Endpoint ${path} is not implemented by the backend.`,
          "ENDPOINT_NOT_IMPLEMENTED",
          response.status
        );
      }

      if (!response.ok) {
        throw new AegisClientError(
          `Backend upload failed with HTTP ${response.status}.`,
          "UNKNOWN_API_ERROR",
          response.status
        );
      }

      const json = await parseJson(response);
      const parsed = schema.safeParse(json);

      if (!parsed.success) {
        throw new AegisClientError(
          `Invalid response schema from ${path}.`,
          "INVALID_RESPONSE_SCHEMA",
          response.status,
          parsed.error.flatten()
        );
      }

      return parsed.data;
    } catch (error) {
      if (error instanceof AegisClientError) throw error;

      if (error instanceof DOMException && error.name === "AbortError") {
        throw new AegisClientError(`Request to ${path} timed out.`, "REQUEST_TIMEOUT");
      }

      throw new AegisClientError(
        `Backend unavailable at ${appConfig.apiUrl}.`,
        "BACKEND_UNAVAILABLE",
        undefined,
        error
      );
    } finally {
      window.clearTimeout(timeout);
    }
  }

  getStatus() {
    return this.request("/status", statusResponseSchema);
  }

  getEvents() {
    return this.request("/events", eventsResponseSchema);
  }

  getTracks() {
    return this.request("/tracks", tracksResponseSchema);
  }

  getStatistics() {
    return this.request("/statistics", statisticsResponseSchema);
  }

  submitSemanticQuery(input: z.infer<typeof semanticQueryRequestSchema>) {
    const body = semanticQueryRequestSchema.parse(input);
    return this.request("/semantic/query", semanticQueryResponseSchema, {
      method: "POST",
      body
    });
  }

  getSemanticResults() {
    return this.request("/semantic/results", semanticResultsResponseSchema);
  }

  getCameras() {
    return this.request("/cameras", camerasResponseSchema);
  }

  createCamera(input: CameraCreateInput) {
    return this.request("/cameras", cameraSchema, {
      method: "POST",
      body: input
    });
  }

  updateCamera(cameraId: string, input: CameraUpdateInput) {
    return this.request(`/cameras/${encodeURIComponent(cameraId)}`, cameraSchema, {
      method: "PATCH",
      body: input
    });
  }

  deleteCamera(cameraId: string) {
    return this.request(`/cameras/${encodeURIComponent(cameraId)}`, z.object({ message: z.string() }), {
      method: "DELETE"
    });
  }

  startCamera(cameraId: string) {
    return this.request(`/cameras/${encodeURIComponent(cameraId)}/start`, cameraSchema, {
      method: "POST"
    });
  }

  stopCamera(cameraId: string) {
    return this.request(`/cameras/${encodeURIComponent(cameraId)}/stop`, cameraSchema, {
      method: "POST"
    });
  }

  getCameraEvents(cameraId: string) {
    return this.request(`/cameras/${encodeURIComponent(cameraId)}/events`, cameraEventsResponseSchema);
  }

  getCameraDetections(cameraId: string) {
    return this.request(`/cameras/${encodeURIComponent(cameraId)}/detections`, cameraDetectionsResponseSchema);
  }

  getCameraOverlays(cameraId: string) {
    return this.request(`/cameras/${encodeURIComponent(cameraId)}/overlays`, cameraOverlayResponseSchema);
  }

  testCameraConnection(input: CameraCreateInput) {
    return this.request("/cameras/test-connection", cameraConnectionTestResponseSchema, {
      method: "POST",
      body: input,
      timeoutMs: 30000
    });
  }

  sendBrowserFrame(cameraId: string, frame: string) {
    return this.request("/camera/browser-frame", browserFrameResponseSchema, {
      method: "POST",
      body: {
        camera_id: cameraId,
        frame
      },
      timeoutMs: 30000
    });
  }

  uploadVideo(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    return this.upload("/videos/upload", videoUploadResponseSchema, formData);
  }

  processVideo(videoId: string, cameraId?: string) {
    return this.request(`/videos/${encodeURIComponent(videoId)}/process`, cameraSchema, {
      method: "POST",
      body: {
        camera_id: cameraId || undefined
      },
      timeoutMs: 30000
    });
  }
}

export const aegisApiClient = new AegisApiClient();
