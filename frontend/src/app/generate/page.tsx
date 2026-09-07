import type { Metadata } from "next";

import { EditorGenerate } from "@/components/editor/editor-generate";
import { AUTH_ENABLED } from "@/lib/auth/config";
import { GenerateWorkspace } from "@/components/generate-workspace";

export const metadata: Metadata = { title: "Generate" };

export default function GeneratePage() {
  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="mb-14 max-w-3xl sm:mb-20">
        <p className="eyebrow">Generate</p>
        <h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">
          Your idea. Their voice.
        </h1>
        <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground">
          Choose a person, platform, and angle. Shape the emotion and viewpoint, then edit
          and re-voice while keeping your structure.
        </p>
      </header>
      {AUTH_ENABLED ? <EditorGenerate /> : <GenerateWorkspace />}
    </div>
  );
}
