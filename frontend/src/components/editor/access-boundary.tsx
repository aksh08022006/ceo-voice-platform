"use client";

import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { AccountMenu } from "@/components/auth/account-menu";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import { editorApi } from "@/lib/editor-api";
import type { EditorActor } from "@/lib/editor-types";

export function EditorAccessBoundary({ children }: { children: (actor: EditorActor) => ReactNode }) {
  const session = useQuery({ queryKey: ["editor", "session"], queryFn: editorApi.session, retry: false });
  if (session.isPending) return <div className="space-y-4" role="status"><p className="text-sm text-muted-foreground">Checking workspace access…</p><Skeleton className="h-48 w-full" /></div>;
  if (session.error) {
    const pendingAccess = session.error instanceof ApiError && session.error.status === 403;
    const needsVerification = pendingAccess && /verify your email/i.test(session.error.message);
    return <section className="max-w-lg rounded-xl border border-border p-7"><h1 className="font-display text-3xl font-medium">{needsVerification ? "Verify your work email" : pendingAccess ? "Your account is ready. Access is pending." : "Workspace could not be loaded"}</h1><p className="mt-4 text-sm leading-7 text-muted-foreground" role={pendingAccess ? "status" : "alert"}>{needsVerification ? "Follow the verification link in your inbox, then check again. Your email must be verified before workspace membership can be checked." : pendingAccess ? "An administrator must add your account to the Narrative Company workspace before you can view or create drafts. You can check again after access is granted, or sign out to use another account." : session.error.message}</p><div className="mt-6 flex flex-wrap gap-3"><Button disabled={session.isFetching} onClick={() => session.refetch()} variant="secondary">{session.isFetching ? "Checking…" : pendingAccess ? "Check access again" : "Retry loading workspace"}</Button><AccountMenu /></div></section>;
  }
  return children(session.data);
}
