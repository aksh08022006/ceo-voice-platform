"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth/client";
import { AUTH_ENABLED } from "@/lib/auth/config";

export function AccountMenu() {
  return AUTH_ENABLED ? <SignedInAccount /> : null;
}

function SignedInAccount() {
  const { data: session, isPending } = authClient.useSession();
  const queryClient = useQueryClient();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);

  async function signOut() {
    setPending(true);
    setError(false);
    try {
      const result = await authClient.signOut();
      if (result.error) throw new Error("Sign-out failed.");
      queryClient.clear();
      try {
        for (const key of Object.keys(window.sessionStorage)) {
          if (key.startsWith("ceo-voice:")) window.sessionStorage.removeItem(key);
        }
      } catch { /* Restricted browser storage may be unavailable. */ }
      router.replace("/auth/sign-in");
      router.refresh();
    } catch {
      setError(true);
      setPending(false);
    }
  }

  if (isPending) return <span className="px-3 text-xs text-muted-foreground" role="status">Loading account…</span>;
  if (!session?.user) return <Link className="rounded-md px-3 py-2 text-sm" href="/auth/sign-in">Sign in</Link>;
  return <div className="flex items-center gap-2"><span className="hidden max-w-32 truncate text-xs text-muted-foreground xl:block">{session.user.name}</span><Button disabled={pending} onClick={signOut} size="sm" variant="ghost">{pending ? "Signing out…" : "Sign out"}</Button>{error ? <span className="text-xs text-red-600" role="alert">Could not sign out. Retry.</span> : null}</div>;
}
