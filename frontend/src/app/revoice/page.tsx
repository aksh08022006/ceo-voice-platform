import type { Metadata } from "next";
import { Suspense } from "react";

import { RevoiceWorkspace } from "@/components/revoice-workspace";

export const metadata: Metadata = { title: "Re-Voice" };

export default function RevoicePage() {
  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="mb-14 max-w-3xl sm:mb-20">
        <p className="eyebrow">Re-Voice</p>
        <h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">
          Keep the edit. Restore the voice.
        </h1>
        <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground">
          Re-Voice checks edited regions, paragraph order, and recognized anchors such as names,
          numbers, and links. Review the result for meaning and voice.
        </p>
      </header>
      <Suspense fallback={<p className="text-muted-foreground">Loading workflow…</p>}><RevoiceWorkspace /></Suspense>
    </div>
  );
}
