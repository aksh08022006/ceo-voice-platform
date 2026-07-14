"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Copy } from "lucide-react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ReportSection } from "@/components/report-section";
import { Button, buttonStyles } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { generatedDraft, structureEvidence, voiceEvidence } from "@/lib/demo-data";

const generationSchema = z.object({
  ceo: z.string().min(1, "Select a CEO profile."),
  platform: z.enum(["linkedin", "x"]),
  contentType: z.enum(["post", "thread", "announcement"]),
  idea: z.string().min(20, "Describe the idea in at least 20 characters.").max(1200),
  constraints: z.string().max(600).optional(),
});

type GenerationForm = z.infer<typeof generationSchema>;

async function generateDraft(form: GenerationForm) {
  await new Promise((resolve) => setTimeout(resolve, 850));
  return { content: generatedDraft, latency: 842, evidenceCount: 7, profile: form.ceo };
}

export function GenerateWorkspace() {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<GenerationForm>({
    resolver: zodResolver(generationSchema),
    defaultValues: {
      ceo: "ali-ghodsi",
      platform: "linkedin",
      contentType: "post",
      idea: "Explain why clear decision ownership helps technology teams execute faster.",
      constraints: "Avoid hype. End with one practical question.",
    },
  });
  const generation = useMutation({
    mutationFn: generateDraft,
    onSuccess: () => toast.success("Draft generated with a complete evidence trace."),
    onError: () => toast.error("Generation failed. No profile or request data was changed."),
  });

  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(18rem,0.72fr)_minmax(0,1.28fr)] lg:gap-16">
      <form className="space-y-6" onSubmit={handleSubmit((values) => generation.mutate(values))}>
        <Field label="CEO" error={errors.ceo?.message}>
          <Select aria-invalid={Boolean(errors.ceo)} {...register("ceo")}>
            <option value="ali-ghodsi">Ali Ghodsi · Published</option>
            <option value="matei-zaharia">Matei Zaharia · Published</option>
            <option value="jensen-huang" disabled>Jensen Huang · Review required</option>
          </Select>
        </Field>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
          <Field label="Platform" error={errors.platform?.message}>
            <Select {...register("platform")}>
              <option value="linkedin">LinkedIn</option>
              <option value="x">X</option>
            </Select>
          </Field>
          <Field label="Content type" error={errors.contentType?.message}>
            <Select {...register("contentType")}>
              <option value="post">Post</option>
              <option value="thread">Thread</option>
              <option value="announcement">Announcement</option>
            </Select>
          </Field>
        </div>
        <Field label="Idea" error={errors.idea?.message}>
          <Textarea aria-invalid={Boolean(errors.idea)} rows={7} {...register("idea")} />
        </Field>
        <Field label="Constraints" error={errors.constraints?.message} optional>
          <Input placeholder="Required phrase, CTA, tone, or factual boundary" {...register("constraints")} />
        </Field>
        <Button className="w-full sm:w-auto" disabled={generation.isPending} size="lg" type="submit">
          {generation.isPending ? "Compiling evidence…" : "Generate draft"}
          {!generation.isPending ? <ArrowRight aria-hidden="true" className="h-4 w-4" /> : null}
        </Button>
      </form>

      <section aria-live="polite" aria-busy={generation.isPending}>
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div>
            <p className="eyebrow">Generated draft</p>
            <p className="mt-2 text-xs text-muted-foreground">LinkedIn · Ali Ghodsi · HVM v4.2</p>
          </div>
          {generation.data ? (
            <Button
              aria-label="Copy generated draft"
              onClick={() => {
                void navigator.clipboard.writeText(generation.data.content);
                toast.success("Draft copied.");
              }}
              size="icon"
              variant="ghost"
            >
              <Copy aria-hidden="true" className="h-4 w-4" />
            </Button>
          ) : null}
        </div>

        {generation.isPending ? (
          <div className="space-y-4 py-10" role="status">
            <Skeleton className="h-5 w-4/5" />
            <Skeleton className="h-5 w-3/5" />
            <Skeleton className="mt-8 h-5 w-full" />
            <Skeleton className="h-5 w-11/12" />
            <Skeleton className="mt-8 h-5 w-5/6" />
            <span className="sr-only">Generating draft</span>
          </div>
        ) : (
          <article className="min-h-[30rem] whitespace-pre-wrap py-10 font-display text-xl leading-[1.65] tracking-[-0.015em] sm:text-2xl">
            {generation.data?.content ?? generatedDraft}
          </article>
        )}

        <div className="border-t border-border">
          <ReportSection title="Generation report">
            <dl className="grid grid-cols-2 gap-5 sm:grid-cols-4">
              <Metric label="Model" value="governed-demo" />
              <Metric label="Latency" value={`${generation.data?.latency ?? 842} ms`} />
              <Metric label="Evidence" value={`${generation.data?.evidenceCount ?? 7} units`} />
              <Metric label="Validation" value="Passed" />
            </dl>
          </ReportSection>
          <ReportSection title="Voice features used">
            <EvidenceList items={voiceEvidence} />
          </ReportSection>
          <ReportSection title="Structural features used">
            <EvidenceList items={structureEvidence} />
          </ReportSection>
          <ReportSection title="Evidence and constraints">
            <p>
              Seven evidence units support the selected features. One negative constraint prevented
              unsupported superlatives; the user CTA and paragraph budget were preserved.
            </p>
          </ReportSection>
        </div>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link className={buttonStyles({ variant: "secondary" })} href="/revoice">
            Review and Re-Voice
          </Link>
          <Link className={buttonStyles({ variant: "ghost" })} href="/evaluation">
            Inspect evaluation
          </Link>
        </div>
      </section>
    </div>
  );
}

function Field({
  label,
  error,
  optional,
  children,
}: {
  label: string;
  error?: string;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm font-medium">
      <span className="mb-2 flex items-center justify-between">
        {label}
        {optional ? <span className="text-xs font-normal text-muted-foreground">Optional</span> : null}
      </span>
      {children}
      {error ? <span className="mt-2 block text-xs text-primary">{error}</span> : null}
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-sm text-foreground">{value}</dd>
    </div>
  );
}

function EvidenceList({ items }: { items: readonly { label: string; confidence: string; source: string }[] }) {
  return (
    <ul className="divide-y divide-border">
      {items.map((item) => (
        <li className="grid gap-1 py-3 first:pt-0 sm:grid-cols-[1fr_auto]" key={item.source}>
          <span className="text-foreground">{item.label}</span>
          <span className="font-mono text-xs">{item.confidence}</span>
          <span className="font-mono text-[10px] sm:col-span-2">{item.source}</span>
        </li>
      ))}
    </ul>
  );
}
