import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";

import { EditorWorkspace } from "@/components/editor/editor-workspace";
import { AUTH_ENABLED } from "@/lib/auth/config";

export const metadata: Metadata = { title: "Workspace" };

export default function WorkspacePage() {
  return <div className="page-shell py-12 sm:py-16">{AUTH_ENABLED ? <Suspense fallback={<p className="text-muted-foreground">Loading workspace…</p>}><EditorWorkspace /></Suspense> : <div><h1 className="font-display text-3xl">Write your next draft</h1><p className="mt-4 text-muted-foreground">Use the generator to write and refine a draft in this browser.</p><Link className="mt-6 inline-block underline" href="/generate">Open generator</Link></div>}</div>;
}
