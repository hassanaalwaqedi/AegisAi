"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { aegisApiClient } from "@/lib/api-client";

export const queryKeys = {
  status: ["status"] as const,
  events: ["events"] as const,
  tracks: ["tracks"] as const,
  statistics: ["statistics"] as const,
  semanticResults: ["semantic-results"] as const,
  cameras: ["cameras"] as const,
  cameraEvents: (cameraId: string) => ["camera-events", cameraId] as const,
  cameraDetections: (cameraId: string) => ["camera-detections", cameraId] as const
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

export function useTracksQuery() {
  return useQuery({
    queryKey: queryKeys.tracks,
    queryFn: () => aegisApiClient.getTracks()
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
    queryFn: () => aegisApiClient.getSemanticResults()
  });
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
