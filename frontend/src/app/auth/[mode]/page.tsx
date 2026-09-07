import Link from "next/link";
import { notFound } from "next/navigation";

import { AuthForm } from "@/components/auth/auth-form";
import { safeReturnPath } from "@/lib/auth/config";
import { serverAuthConfigured } from "@/lib/auth/server";

export const dynamic = "force-dynamic";

export default async function AuthPage({ params, searchParams }: {
  params: Promise<{ mode: string }>;
  searchParams: Promise<{ redirectTo?: string; redirect?: string; callbackURL?: string }>;
}) {
  const { mode } = await params;
  if (mode !== "sign-in" && mode !== "sign-up") notFound();
  if (!serverAuthConfigured()) return <div className="page-shell py-16"><h1 className="font-display text-3xl">You can start writing</h1><p className="mt-4 text-muted-foreground">No sign-in is needed to use the generator.</p><Link className="mt-6 inline-block underline" href="/generate">Open generator</Link></div>;
  const query = await searchParams;
  return <div className="page-shell"><AuthForm mode={mode} returnTo={safeReturnPath(query.redirectTo ?? query.redirect ?? query.callbackURL)} /></div>;
}
