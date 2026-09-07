"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authClient } from "@/lib/auth/client";
import { authFailureMessage } from "@/lib/auth/errors";
import { safeReturnPath } from "@/lib/auth/config";

type AuthMode = "sign-in" | "sign-up";

export function AuthForm({ mode, returnTo }: { mode: AuthMode; returnTo: string }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verificationPending, setVerificationPending] = useState(false);
  const [verificationCode, setVerificationCode] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const target = safeReturnPath(returnTo);

  async function continueWithGoogle() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const result = await authClient.signIn.social({ provider: "google", callbackURL: target });
      if (result.error) setError(authFailureMessage(result.error));
    } catch (failure) {
      setError(authFailureMessage(failure));
    } finally {
      setPending(false);
    }
  }

  async function resendVerification() {
    if (pending) return;
    setPending(true);
    setError(null);
    setNotice(null);
    try {
      const result = await authClient.emailOtp.sendVerificationOtp({ email: email.trim(), type: "email-verification" });
      if (result.error) setError(authFailureMessage(result.error));
      else setNotice("A new verification code has been requested. Check your inbox.");
    } catch (failure) {
      setError(authFailureMessage(failure));
    } finally {
      setPending(false);
    }
  }

  async function verifyEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const result = await authClient.emailOtp.verifyEmail({ email: email.trim(), otp: verificationCode.trim() });
      if (result.error) {
        setError(authFailureMessage(result.error));
        return;
      }
      setVerificationCode("");
      const session = await authClient.getSession();
      router.replace(session.data?.user ? target : `/auth/sign-in?redirectTo=${encodeURIComponent(target)}`);
      router.refresh();
      setVerificationPending(false);
      setNotice("Email verified. You can now sign in.");
    } catch (failure) {
      setError(authFailureMessage(failure));
    } finally {
      setPending(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    setNotice(null);
    try {
      const result = mode === "sign-up"
        ? await authClient.signUp.email({ name: name.trim(), email: email.trim(), password, callbackURL: target })
        : await authClient.signIn.email({ email: email.trim(), password, callbackURL: target });
      if (result.error) {
        if (result.error.code === "EMAIL_NOT_VERIFIED") {
          setPassword("");
          setVerificationPending(true);
          setNotice("Enter the verification code from your email, or request a new one below.");
          return;
        }
        setError(authFailureMessage(result.error));
        return;
      }
      setPassword("");
      const session = await authClient.getSession();
      if (!session.data?.user) {
        setVerificationPending(true);
        return;
      }
      router.replace(target);
      router.refresh();
    } catch (failure) {
      setError(authFailureMessage(failure));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mx-auto max-w-md py-16">
      <p className="section-label">Narrative Company workspace</p>
      <h1 className="mt-3 font-display text-3xl font-semibold">{mode === "sign-up" ? "Create your account" : "Welcome back"}</h1>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">Sign in to save drafts and review them with your team. Workspace access is granted by an administrator.</p>
      {error ? <p className="mt-5 rounded-md border border-red-500/30 p-3 text-sm text-red-600 dark:text-red-400" role="alert">{error}</p> : null}
      {notice ? <p className="mt-5 text-sm text-muted-foreground" role="status">{notice}</p> : null}
      {verificationPending ? (
        <form className="mt-6 space-y-4 rounded-lg border border-border bg-surface p-5" onSubmit={verifyEmail}>
          <p className="font-medium">Check your email</p>
          <p className="text-sm text-muted-foreground">Enter the code sent to {email.trim()}. Creating an account does not grant workspace access.</p>
          <label className="block text-sm font-medium" htmlFor="auth-code">Verification code<Input autoComplete="one-time-code" className="mt-2" id="auth-code" inputMode="numeric" maxLength={10} minLength={6} onChange={(event) => setVerificationCode(event.target.value)} pattern="[0-9]{6,10}" required value={verificationCode} /></label>
          <Button className="w-full" disabled={pending} type="submit">{pending ? "Please wait…" : "Verify email"}</Button>
          <Button className="w-full" disabled={pending} onClick={resendVerification} variant="secondary">Send a new code</Button>
          <Link className="inline-block text-sm underline underline-offset-4" href={`/auth/sign-in?redirectTo=${encodeURIComponent(target)}`}>Return to sign in</Link>
        </form>
      ) : (
        <form className="mt-8 space-y-5" onSubmit={submit}>
          <Button className="w-full" disabled={pending} onClick={continueWithGoogle} variant="secondary">Continue with Google</Button>
          <p className="text-center text-xs text-muted-foreground">or use your email and password</p>
          {mode === "sign-up" ? <label className="block text-sm font-medium" htmlFor="auth-name">Your name<Input autoComplete="name" className="mt-2" id="auth-name" maxLength={100} onChange={(event) => setName(event.target.value)} required value={name} /></label> : null}
          <label className="block text-sm font-medium" htmlFor="auth-email">Work email<Input autoComplete="email" className="mt-2" id="auth-email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} /></label>
          <label className="block text-sm font-medium" htmlFor="auth-password">Password<Input autoComplete={mode === "sign-up" ? "new-password" : "current-password"} className="mt-2" id="auth-password" maxLength={128} minLength={mode === "sign-up" ? 12 : 1} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></label>
          {mode === "sign-up" ? <p className="text-xs text-muted-foreground">Use at least 12 characters.</p> : null}
          <Button className="w-full" disabled={pending} type="submit">{pending ? "Please wait…" : mode === "sign-up" ? "Create account" : "Sign in"}</Button>
          <p className="text-sm text-muted-foreground">{mode === "sign-up" ? "Already have an account? " : "New here? "}<Link className="text-foreground underline underline-offset-4" href={`/auth/${mode === "sign-up" ? "sign-in" : "sign-up"}?redirectTo=${encodeURIComponent(target)}`}>{mode === "sign-up" ? "Sign in" : "Create an account"}</Link></p>
        </form>
      )}
    </section>
  );
}
