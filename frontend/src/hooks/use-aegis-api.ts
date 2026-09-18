"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { aegisApiClient, type CameraUpdateInput } from "@/lib/api-client";

export const queryKeys = {
  status: ["status"] as const,
  events: ["events"] as const,
  alerts: ["alerts"] as const,
  alertCount: ["alert-count"] as const,
  incidents: ["incidents"] as const,
  evidence: ["persisted-evidence"] as const,
  tracks: ["tracks"] as const,
  statistics: ["statistics"] as const,
  semanticResults: ["semantic-results"] as const,
  evidenceSearchStatus: ["evidence-search-status"] as const,
  evidenceSearch: (request: unknown) => ["evidence-search", request] as const,
  evidenceSearchDetail: (eventId: string) => ["evidence-search-detail", eventId] as const,
  cameras: ["cameras"] as const,
  cameraEvents: (cameraId: string) => ["camera-events", cameraId] as const,
  cameraDetections: (cameraId: string) => ["camera-detections", cameraId] as const,
  cameraOverlays: (cameraId: string) => ["camera-overlays", cameraId] as const
};

export function useStatusQuery() {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: () => aegisApiClient.getStatus()
  });
}

export function useEventsQuery() {
  return useQuery({
    queryKey: queryKeys.events,
    queryFn: () => aegisApiClient.getEvents()
  });
}

export function useAlertsQuery(activeOnly = false, limit?: number) {
  return useQuery({
    queryKey: [...queryKeys.alerts, activeOnly ? "active" : "all", limit ?? "default"],
    queryFn: () => aegisApiClient.getAlerts(activeOnly, limit),
    refetchInterval: 3000
  });
}

export function useAlertCountQuery() {
  return useQuery({
    queryKey: queryKeys.alertCount,
    queryFn: () => aegisApiClient.getAlertCount(),
    refetchInterval: 3000
  });
}

export function useIncidentsQuery() {
  return useQuery({
    queryKey: queryKeys.incidents,
    queryFn: () => aegisApiClient.getIncidents(),
    refetchInterval: 5000
  });
}

export function usePersistedEvidenceQuery() {
  return useQuery({
    queryKey: queryKeys.evidence,
    queryFn: () => aegisApiClient.getPersistedEvidence(),
    refetchInterval: 5000
  });
}

export function useTracksQuery() {
  return useQuery({
    queryKey: queryKeys.tracks,
    queryFn: () => aegisApiClient.getTracks(),
    refetchInterval: 3000
  });
}

export function useStatisticsQuery() {
  return useQuery({
    queryKey: queryKeys.statistics,
    queryFn: () => aegisApiClient.getStatistics()
  });
}

export function useSemanticResultsQuery() {
  return useQuery({
    queryKey: queryKeys.semanticResults,
    queryFn: () => aegisApiClient.getSemanticResults(),
    refetchInterval: 5000
  });
}

export function useEvidenceSearchStatusQuery() {
  return useQuery({ queryKey: queryKeys.evidenceSearchStatus, queryFn: () => aegisApiClient.getEvidenceSearchStatus(), refetchInterval: 10000 });
}

export function useEvidenceSearchQuery(request: Parameters<typeof aegisApiClient.searchEvidence>[0], enabled: boolean) {
  return useQuery({ queryKey: queryKeys.evidenceSearch(request), queryFn: () => aegisApiClient.searchEvidence(request), enabled, staleTime: 0 });
}

export function useEvidenceSearchDetailQuery(eventId: string | null) {
  return useQuery({ queryKey: queryKeys.evidenceSearchDetail(eventId ?? "none"), queryFn: () => aegisApiClient.getEvidenceSearchDetail(eventId!), enabled: Boolean(eventId) });
}

export function useSemanticQueryMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (prompt: string) =>
      aegisApiClient.submitSemanticQuery({
        prompt,
        priority: 50
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.semanticResults });
    }
  });
}

export function useCamerasQuery() {
  return useQuery({
    queryKey: queryKeys.cameras,
    queryFn: () => aegisApiClient.getCameras(),
    refetchInterval: 3000
  });
}

export function useCameraEventsQuery(cameraId?: string) {
  return useQuery({
    queryKey: queryKeys.cameraEvents(cameraId ?? ""),
    queryFn: () => aegisApiClient.getCameraEvents(cameraId ?? ""),
    enabled: Boolean(cameraId),
    refetchInterval: 5000
  });
}

export function useCameraDetectionsQuery(cameraId?: string) {
  return useQuery({
    queryKey: queryKeys.cameraDetections(cameraId ?? ""),
    queryFn: () => aegisApiClient.getCameraDetections(cameraId ?? ""),
    enabled: Boolean(cameraId),
    refetchInterval: 3000
  });
}

export function useCameraOverlaysQuery(cameraId?: string) {
  return useQuery({
    queryKey: queryKeys.cameraOverlays(cameraId ?? ""),
    queryFn: () => aegisApiClient.getCameraOverlays(cameraId ?? ""),
    enabled: Boolean(cameraId),
    refetchInterval: 3000
  });
}

export function useCreateCameraMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: aegisApiClient.createCamera.bind(aegisApiClient),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras });
      void queryClient.invalidateQueries({ queryKey: queryKeys.status });
    }
  });
}

export function useUpdateCameraMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ cameraId, input }: { cameraId: string; input: CameraUpdateInput }) => aegisApiClient.updateCamera(cameraId, input),
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras });
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameraOverlays(variables.cameraId) });
    }
  });
}

export function useCameraConnectionTestMutation() {
  return useMutation({
    mutationFn: aegisApiClient.testCameraConnection.bind(aegisApiClient)
  });
}

export function useStartCameraMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (cameraId: string) => aegisApiClient.startCamera(cameraId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras });
      void queryClient.invalidateQueries({ queryKey: queryKeys.status });
    }
  });
}

export function useStopCameraMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (cameraId: string) => aegisApiClient.stopCamera(cameraId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras });
      void queryClient.invalidateQueries({ queryKey: queryKeys.status });
    }
  });
}

export function useDeleteCameraMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (cameraId: string) => aegisApiClient.deleteCamera(cameraId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras });
      void queryClient.invalidateQueries({ queryKey: queryKeys.status });
    }
  });
}

export function useBrowserFrameMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ cameraId, frame }: { cameraId: string; frame: string }) =>
      aegisApiClient.sendBrowserFrame(cameraId, frame),
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameraEvents(variables.cameraId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameraDetections(variables.cameraId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.tracks });
      void queryClient.invalidateQueries({ queryKey: queryKeys.events });
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts });
      void queryClient.invalidateQueries({ queryKey: queryKeys.incidents });
      void queryClient.invalidateQueries({ queryKey: queryKeys.evidence });
      void queryClient.invalidateQueries({ queryKey: queryKeys.statistics });
    }
  });
}

export function useUploadVideoMutation() {
  return useMutation({
    mutationFn: (file: File) => aegisApiClient.uploadVideo(file)
  });
}

export function useProcessVideoMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ videoId, cameraId }: { videoId: string; cameraId?: string }) =>
      aegisApiClient.processVideo(videoId, cameraId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras });
      void queryClient.invalidateQueries({ queryKey: queryKeys.status });
    }
  });
}
