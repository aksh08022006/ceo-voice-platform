import type { Metadata } from "next";

import { GenerateWorkspace } from "@/components/generate-workspace";

export const metadata: Metadata = { title: "Generate" };

export default function GeneratePage() {
  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="mb-14 max-w-3xl sm:mb-20">
        <p className="eyebrow">Generate</p>
        <h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">
          Turn an idea into accountable communication.
        </h1>
        <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground">
          Voice and structure are retrieved independently. Every decision remains traceable to a
          published release and its evidence.
        </p>
      </header>
      <GenerateWorkspace />
    </div>
  );
}
