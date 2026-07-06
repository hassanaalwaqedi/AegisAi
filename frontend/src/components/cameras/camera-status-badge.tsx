import { Badge } from "@/components/ui/badge";
import type { CameraConnectionStatus } from "@/types";

const statusLabel: Record<CameraConnectionStatus, string> = {
  online: "Online",
  offline: "Offline",
  connecting: "Connecting",
  reconnecting: "Reconnecting",
  error: "Error",
  stopped: "Stopped"
};

export function CameraStatusBadge({ status }: { status: CameraConnectionStatus }) {
  const variant =
    status === "online" ? "success" : status === "connecting" || status === "reconnecting" ? "warning" : status === "error" ? "danger" : "outline";

  return <Badge variant={variant}>{statusLabel[status]}</Badge>;
}
