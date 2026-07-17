"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { ReportSection } from "@/components/report-section";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export default function ProfilePage() {
  const slug = useParams<{ slug: string }>().slug;
  const query = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });

  if (query.isPending) {
    return (
      <div className="page-shell py-24">
        <Skeleton className="h-36 w-full" />
      </div>
    );
  }

  const profile = query.data?.find((item) => item.slug === slug);
  if (!profile) {
    return <div className="page-shell py-24 text-muted-foreground">Profile not found.</div>;
  }

  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="border-b border-border pb-14">
        <div className="flex items-center gap-3">
          <p className="eyebrow">Voice profile</p>
          <Badge className="border-primary/30 text-primary">{profile.status}</Badge>
        </div>
        <h1 className="mt-5 font-display text-6xl font-medium tracking-[-0.055em] sm:text-8xl">
          {profile.name}
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">{profile.role}</p>
        <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground">{profile.summary}</p>
      </header>
      <div className="grid gap-16 py-16 lg:grid-cols-[0.7fr_1.3fr]">
        <section>
          <p className="eyebrow">Governance note</p>
          <p className="mt-6 font-display text-2xl leading-10 tracking-[-0.02em]">
            This development profile was built from operator-transcribed public posts. It supports
            full-system testing, but incomplete provenance, timestamps, reuse authority, and
            independent fidelity review prevent a production identity claim.
          </p>
        </section>
        <section className="border-t border-border">
          <ReportSection title="Representation">
            <p>
              The browser workflow builds the profile from its corpus, publishes an immutable HVM
              release, compiles context, and retrieves bounded evidence before generation.
            </p>
          </ReportSection>
          <ReportSection title="Inspection">
            <p>
              Generate a draft with this profile to inspect the live feature, evidence, timing,
              validation, and evaluation projections.
            </p>
          </ReportSection>
        </section>
      </div>
    </div>
  );
}
