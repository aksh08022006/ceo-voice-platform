import type { Metadata } from "next";

import { ProfilesList } from "@/components/profiles-list";

export const metadata: Metadata = { title: "Profiles" };

export default function ProfilesPage() {
  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="mb-16 max-w-3xl">
        <p className="eyebrow">Profiles</p>
        <h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">
          Inspectable voice knowledge.
        </h1>
        <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground">
          Inspect coverage, evidence, version history, and authorization before a profile reaches
          generation.
        </p>
      </header>

      <ProfilesList />
    </div>
  );
}
