"use client";

import { AlertCircle, CheckCircle2, RadioTower, WifiOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { getErrorMessage } from "@/lib/errors";
import type { WebSocketConnectionState } from "@/types";

type EndpointQuery = {
  isLoading: boolean;
  isError: boolean;
  isSuccess: boolean;
  error: unknown;
};

type ApiStatusBannerProps = {
  endpoints: Array<{
    name: string;
    query: EndpointQuery;
  }>;
  websocketState?: WebSocketConnectionState;
  websocketError?: Error | null;
};

export function ApiStatusBanner({ endpoints, websocketState, websocketError }: ApiStatusBannerProps) {
  const loading = endpoints.some((endpoint) => endpoint.query.isLoading);
  const failures = endpoints.filter((endpoint) => endpoint.query.isError);
  const successes = endpoints.filter((endpoint) => endpoint.query.isSuccess);
  const allFailed = endpoints.length > 0 && failures.length === endpoints.length;

  if (loading && successes.length === 0) {
    return (
      <div className="mb-5 rounded-lg border border-white/10 bg-white/[0.045] px-4 py-3 text-sm text-slate-300">
        Checking AegisAI backend connection...
      </div>
    );
  }

  if (allFailed) {
    return (
      <div className="mb-5 rounded-lg border border-rose-400/25 bg-rose-500/[0.07] px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-rose-300" aria-hidden />
            <div>
              <p className="text-sm font-semibold text-rose-100">Backend unavailable</p>
              <p className="mt-1 text-sm text-rose-100/75">{getErrorMessage(failures[0]?.query.error)}</p>
            </div>
          </div>
          <Badge variant="danger">No endpoint data</Badge>
        </div>
      </div>
    );
  }

  if (failures.length > 0) {
    return (
      <div className="mb-5 rounded-lg border border-amber-300/20 bg-amber-300/[0.06] px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-200" aria-hidden />
            <div>
              <p className="text-sm font-semibold text-amber-100">Partial backend capability</p>
              <p className="mt-1 text-sm text-amber-100/75">
                {failures.map((failure) => failure.name).join(", ")} returned an error. Available panels are still using live backend data.
              </p>
            </div>
          </div>
          <Badge variant="warning">{successes.length}/{endpoints.length} endpoints healthy</Badge>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-5 rounded-lg border border-emerald-300/20 bg-emerald-400/[0.055] px-4 py-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="h-5 w-5 text-emerald-300" aria-hidden />
          <p className="text-sm font-semibold text-emerald-100">Connected to AegisAI backend</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="success">{endpoints.length} endpoints validated</Badge>
          {websocketState ? (
            <Badge variant={websocketState === "connected" ? "success" : "warning"}>
              <RadioTower className="mr-1 h-3.5 w-3.5" aria-hidden />
              WebSocket {websocketState}
            </Badge>
          ) : null}
          {websocketError ? <Badge variant="warning">{websocketError.message}</Badge> : null}
        </div>
      </div>
    </div>
  );
}
