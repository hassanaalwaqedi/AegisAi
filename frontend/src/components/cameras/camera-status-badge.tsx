import { Badge } from "@/components/ui/badge";
import type { CameraConnectionStatus } from "@/types";

const statusLabel: Record<CameraConnectionStatus, string> = {
  online: "Online",
  offline: "Offline",
  connecting: "Connecting",
  reconnecting: "Reconnecting",
  error: "Needs attention",
  stopped: "Stopped",
  failed: "Needs attention",
  unverified: "Not verified",
  disabled: "Disabled"
};

export function CameraStatusBadge({ status }: { status: CameraConnectionStatus }) {
  const variant =
    status === "online" ? "success" : status === "connecting" || status === "reconnecting" || status === "unverified" ? "warning" : status === "error" || status === "failed" ? "danger" : "outline";

  return <Badge variant={variant}>{statusLabel[status]}</Badge>;
}
