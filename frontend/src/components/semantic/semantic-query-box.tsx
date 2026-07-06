"use client";

import { Search } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { useSemanticQueryMutation } from "@/hooks/use-aegis-api";
import { ErrorState } from "@/components/layout/states";

const promptExamples = [
  "detect people carrying weapons",
  "find suspicious loitering near restricted areas",
  "identify crowd density risks"
];

export function SemanticQueryBox() {
  const [prompt, setPrompt] = useState("");
  const mutation = useSemanticQueryMutation();

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Semantic Query</CardTitle>
          <p className="mt-1 text-sm text-slate-400">Submits operator prompts to POST /semantic/query</p>
        </div>
      </CardHeader>

      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (prompt.trim().length >= 3) mutation.mutate(prompt.trim());
        }}
      >
        <label className="block">
          <span className="mb-2 block text-xs uppercase tracking-[0.14em] text-slate-500">Operator prompt</span>
          <Textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} />
        </label>

        <div className="flex flex-wrap gap-2">
          {promptExamples.map((example) => (
            <Button key={example} type="button" variant="secondary" className="h-auto min-h-10 justify-start whitespace-normal text-left" onClick={() => setPrompt(example)}>
              {example}
            </Button>
          ))}
        </div>

        <Button type="submit" disabled={mutation.isPending || prompt.trim().length < 3}>
          <Search className="h-4 w-4" aria-hidden />
          Submit query
        </Button>
      </form>

      {mutation.isSuccess ? (
        <div className="mt-4 rounded-md border border-emerald-300/20 bg-emerald-400/[0.055] p-3 text-sm text-emerald-100">
          {mutation.data.message}
        </div>
      ) : null}

      {mutation.isError ? <div className="mt-4"><ErrorState error={mutation.error} title="Semantic query failed" /></div> : null}
    </Card>
  );
}
