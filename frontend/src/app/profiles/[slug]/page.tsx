import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ReportSection } from "@/components/report-section";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { profiles } from "@/lib/demo-data";

type ProfilePageProps = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return profiles.map((profile) => ({ slug: profile.slug }));
}

export async function generateMetadata({ params }: ProfilePageProps): Promise<Metadata> {
  const { slug } = await params;
  const profile = profiles.find((item) => item.slug === slug);
  return { title: profile?.name ?? "Profile" };
}

export default async function ProfilePage({ params }: ProfilePageProps) {
  const { slug } = await params;
  const profile = profiles.find((item) => item.slug === slug);
  if (!profile) notFound();

  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="grid gap-10 border-b border-border pb-14 lg:grid-cols-[1fr_18rem] lg:items-end">
        <div>
          <div className="flex items-center gap-3">
            <p className="eyebrow">Voice profile</p>
            <Badge className={profile.status === "Published" ? "border-primary/30 text-primary" : undefined}>
              {profile.status}
            </Badge>
          </div>
          <h1 className="mt-5 font-display text-6xl font-medium tracking-[-0.055em] sm:text-8xl">{profile.name}</h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground">{profile.summary}</p>
        </div>
        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-muted-foreground">Evidence coverage</span>
            <span className="font-mono text-xl">{profile.coverage}%</span>
          </div>
          <Progress className="mt-3" value={profile.coverage} />
          <p className="mt-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Active release {profile.version}</p>
        </div>
      </header>

      <div className="grid gap-16 py-16 lg:grid-cols-[0.7fr_1.3fr]">
        <section>
          <p className="eyebrow">Voice summary</p>
          <p className="mt-6 font-display text-2xl leading-10 tracking-[-0.02em]">
            Direct openings, mechanism-led explanations, compact paragraphs, and evidence before
            conclusion. Negative constraints suppress inflated claims and borrowed slogans.
          </p>
        </section>
        <section className="border-t border-border">
          <ReportSection title="Rhetorical features">
            <FeatureRow label="Declarative opening" value="0.96" evidence="24 units" />
            <FeatureRow label="Mechanism before claim" value="0.91" evidence="19 units" />
          </ReportSection>
          <ReportSection title="Formatting and cadence">
            <FeatureRow label="Short paragraph rhythm" value="0.94" evidence="31 units" />
            <FeatureRow label="Question-led close" value="0.82" evidence="12 units" />
          </ReportSection>
          <ReportSection title="Evidence">
            <p>68 evidence units across 42 reviewed documents and three source modalities.</p>
          </ReportSection>
          <ReportSection title="Versions">
            <ol className="space-y-5 border-s border-border ps-5">
              <Timeline version={profile.version} date="12 Jul 2026" note="Active · evidence refresh" />
              <Timeline version="v4.1" date="28 Jun 2026" note="Superseded · calibration update" />
              <Timeline version="v4.0" date="09 Jun 2026" note="Superseded · reviewer approved" />
            </ol>
          </ReportSection>
        </section>
      </div>
    </div>
  );
}

function FeatureRow({ label, value, evidence }: { label: string; value: string; evidence: string }) {
  return (
    <div className="grid grid-cols-[1fr_auto] gap-2 border-b border-border py-3 last:border-0">
      <span className="text-foreground">{label}</span>
      <span className="font-mono text-xs text-foreground">{value}</span>
      <span className="text-xs sm:col-span-2">{evidence}</span>
    </div>
  );
}

function Timeline({ version, date, note }: { version: string; date: string; note: string }) {
  return (
    <li className="relative before:absolute before:-start-[1.45rem] before:top-2 before:h-2 before:w-2 before:rounded-full before:bg-primary">
      <div className="flex items-baseline justify-between gap-4">
        <span className="font-mono text-xs text-foreground">{version}</span>
        <time className="font-mono text-[10px]">{date}</time>
      </div>
      <p className="mt-1 text-xs">{note}</p>
    </li>
  );
}
