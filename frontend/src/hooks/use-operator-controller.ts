"use client";

import { createOperatorRuntime, type OperatorRuntime, type OperatorRuntimeInput } from "@/lib/operator-runtime";

/** React boundary around the pure OperatorController runtime. */
export function useOperatorController(input: OperatorRuntimeInput): OperatorRuntime {
  return createOperatorRuntime(input);
}
