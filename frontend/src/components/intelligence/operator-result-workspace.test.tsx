import { cleanup, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import type { OperatorExecution } from "@/lib/operator-api";
import { OperatorResultWorkspace } from "./operator-result-workspace";

afterEach(cleanup);

describe("Operator result evidence rationale", () => {
  it("shows the stored reason, verification state, and candidate signals", () => {
    const execution: OperatorExecution = {
      action: "EVENT_SEARCH",
      intent: "Investigation",
      answer: "Found one event.",
      panel: "events",
      result: {
        events: [{
          event_id: "evt-1",
          camera_id: "north-gate",
          reason: "Repeated close-contact movement was observed.",
          factors: ["CLOSE_CONTACT_REPEATED", "FAST_MOVEMENT"],
          reason_codes: ["FAST_MOVEMENT", "OPERATOR_REVIEW_REQUIRED"],
          verification_status: "confirmed",
          risk_level: "HIGH",
        }],
      },
      sources: [],
      trace: [],
      response_language: "English",
    };

    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <OperatorResultWorkspace
          execution={execution}
          selectedId="evt-1"
          onOpen={vi.fn()}
          onFindSimilar={vi.fn()}
          onSelect={vi.fn()}
          onRelated={vi.fn()}
        />
      </NextIntlClientProvider>,
    );

    const rationale = screen.getByLabelText("Why Aegis flagged this");
    expect(within(rationale).getByText("Why Aegis flagged this")).toBeInTheDocument();
    expect(within(rationale).getByText("Repeated close-contact movement was observed.")).toBeInTheDocument();
    expect(within(rationale).getByText("Verification: Confirmed")).toBeInTheDocument();
    expect(within(rationale).getByText("Close contact repeated")).toBeInTheDocument();
    expect(within(rationale).getByText("Operator review required")).toBeInTheDocument();
  });
});
