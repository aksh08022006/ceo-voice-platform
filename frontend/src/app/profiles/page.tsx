import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { profiles } from "@/lib/demo-data";

export const metadata: Metadata = { title: "Profiles" };

export default function ProfilesPage() {
  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="mb-16 max-w-3xl">
        <p className="eyebrow">Profiles</p>
        <h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">
          Published voice knowledge.
        </h1>
        <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground">
          Inspect coverage, evidence, version history, and authorization before a profile reaches
          generation.
        </p>
      </header>

      <div className="border-t border-border">
        {profiles.map((profile) => (
          <Link
            className="group grid gap-6 border-b border-border py-8 transition-colors hover:bg-muted/30 sm:grid-cols-[1fr_9rem_4rem_1.5rem] sm:items-center sm:px-3"
            href={`/profiles/${profile.slug}`}
            key={profile.slug}
          >
            <div>
              <h2 className="font-display text-2xl font-medium tracking-tight">{profile.name}</h2>
              <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">{profile.summary}</p>
            </div>
            <Badge className={profile.status === "Published" ? "border-primary/30 text-primary" : undefined}>
              {profile.status}
            </Badge>
            <div>
              <span className="font-mono text-sm">{profile.coverage}%</span>
              <Progress className="mt-2" value={profile.coverage} />
            </div>
            <ArrowRight aria-hidden="true" className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-1" />
          </Link>
        ))}
      </div>
    </div>
  );
}
