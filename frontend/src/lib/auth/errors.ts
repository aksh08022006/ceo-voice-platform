export function authFailureMessage(error: unknown): string {
  const record = typeof error === "object" && error !== null ? error as { code?: unknown; message?: unknown; body?: { code?: unknown } } : null;
  const code = record?.code ?? record?.body?.code;
  if (code === "INVALID_ORIGIN" || record?.message === "Invalid origin") return "Sign-in is not available on this address yet. An administrator needs to complete workspace setup. Please try again later.";
  if (code === "EMAIL_NOT_VERIFIED") return "Verify your email using the code in your inbox, then sign in again.";
  if (code === "INVALID_OTP" || code === "OTP_EXPIRED") return "That verification code is invalid or expired. Check the code or request a new one.";
  if (code === "INVALID_EMAIL_OR_PASSWORD" || code === "INVALID_PASSWORD") return "The email or password was not accepted. Check your details and try again.";
  if (code === "USER_ALREADY_EXISTS" || code === "USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL") return "An account already exists for this email. Sign in to continue.";
  if (code === "PASSWORD_TOO_SHORT") return "Use a password with at least 12 characters.";
  return "Sign-in could not be completed. Check your details and try again. If this continues, contact your workspace administrator.";
}
