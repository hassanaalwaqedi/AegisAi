import { Info } from "lucide-react";
import { getStatusSystem } from "@/lib/data-format";
import type { StatusResponse } from "@/types";

type ModelCapabilityBannerProps = {
  status?: StatusResponse;
};

export function ModelCapabilityBanner({ status }: ModelCapabilityBannerProps) {
  const system = getStatusSystem(status);
  const supportedClasses = system.supported_classes?.length ? system.supported_classes.join(", ") : "person/vehicle detection";

  return (
    <div className="rounded-md border border-signal-cyan/25 bg-signal-cyan/[0.06] p-4 text-sm text-slate-200">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-signal-cyan" aria-hidden />
          <div>
            <p className="font-semibold text-white">Current model supports person/vehicle detection only. Weapon and action recognition are not enabled.</p>
            <p className="mt-1 text-slate-400">Backend model: {system.model_name || "Not returned"} · Supported classes: {supportedClasses}</p>
          </div>
        </div>
        <div className="grid gap-1 text-xs text-slate-300 sm:min-w-[260px]">
          <span>weapon_detection_supported: {String(system.weapon_detection_supported ?? false)}</span>
          <span>action_recognition_supported: {String(system.action_recognition_supported ?? false)}</span>
          <span>pose_estimation_supported: {String(system.pose_estimation_supported ?? false)}</span>
          <span>semantic_verification_supported: {String(system.semantic_verification_supported ?? false)}</span>
        </div>
      </div>
    </div>
  );
}
