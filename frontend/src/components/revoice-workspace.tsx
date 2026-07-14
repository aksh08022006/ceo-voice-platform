"use client";

import { useMutation } from "@tanstack/react-query";
import { ArrowDown } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ReportSection } from "@/components/report-section";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { generatedDraft } from "@/lib/demo-data";

const initialEdit = generatedDraft.replace(
  "Clear ownership removes coordination loops.",
  "Clear ownership removes slow coordination loops.",
);

async function restoreVoice(edited: string) {
  await new Promise((resolve) => setTimeout(resolve, 700));
  return edited.replace("slow coordination loops", "costly coordination loops");
}

export function RevoiceWorkspace() {
  const [edited, setEdited] = useState(initialEdit);
  const restoration = useMutation({
    mutationFn: restoreVoice,
    onSuccess: () => toast.success("Voice restored without changing protected regions."),
    onError: () => toast.error("Re-Voice failed. Your edit remains unchanged."),
  });
  const compared = compareLines(edited, restoration.data ?? edited);

  return (
    <div>
      <div className="grid gap-8 lg:grid-cols-2">
        <Editor label="Original" readOnly value={generatedDraft} />
        <Editor label="Edited" value={edited} onChange={setEdited} />
      </div>
      <div className="flex flex-col items-center py-10">
        <Button
          disabled={restoration.isPending || edited === generatedDraft}
          onClick={() => restoration.mutate(edited)}
          size="lg"
        >
          {restoration.isPending ? "Protecting intent…" : "Re-Voice"}
        </Button>
        <ArrowDown aria-hidden="true" className="mt-6 h-4 w-4 text-muted-foreground" />
      </div>

      <section aria-live="polite" className="border-t border-border pt-10">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Comparison</p>
            <h2 className="mt-4 font-display text-3xl font-medium tracking-tight">Protected meaning. Restored cadence.</h2>
          </div>
          <span className="font-mono text-xs text-muted-foreground">1 region changed</span>
        </div>
        <div className="mt-8 whitespace-pre-wrap border-y border-border py-8 font-display text-lg leading-8 sm:text-xl">
          {compared.map((line, index) => (
            <span
              className={line.changed ? "rounded-sm bg-primary/10 text-foreground" : undefined}
              key={`${index}-${line.text}`}
            >
              {line.text}
              {index < compared.length - 1 ? "\n" : ""}
            </span>
          ))}
        </div>
        <div className="mt-8 border-t border-border">
          <ReportSection title="Re-Voice report">
            <p>
              One editable phrase was adjusted. Paragraph order, factual anchors, argument structure,
              formatting, and CTA intent were preserved. Confidence: 0.94.
            </p>
          </ReportSection>
          <ReportSection title="Voice features strengthened">
            <ul className="space-y-2">
              <li>Concise mechanism language · HVM rhetorical.reasoning.v2</li>
              <li>Direct lexical preference · HVM lexical.specificity.v1</li>
            </ul>
          </ReportSection>
          <ReportSection title="Protected regions">
            <p>Five paragraphs, one CTA, and all factual statements remained immutable.</p>
          </ReportSection>
        </div>
      </section>
    </div>
  );
}

function Editor({
  label,
  value,
  readOnly = false,
  onChange,
}: {
  label: string;
  value: string;
  readOnly?: boolean;
  onChange?: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-3 flex items-center justify-between text-sm font-medium">
        {label}
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {readOnly ? "Protected" : "Human editable"}
        </span>
      </span>
      <Textarea
        className="min-h-[32rem] font-display text-base leading-7"
        onChange={onChange ? (event) => onChange(event.target.value) : undefined}
        readOnly={readOnly}
        value={value}
      />
    </label>
  );
}

function compareLines(before: string, after: string) {
  const beforeLines = before.split("\n");
  return after.split("\n").map((text, index) => ({ text, changed: text !== beforeLines[index] }));
}
