import { NextResponse, type NextRequest } from "next/server";

import { getServerAuth, serverAuthConfigured } from "@/lib/auth/server";

export async function proxy(request: NextRequest) {
  if (!serverAuthConfigured()) return NextResponse.next();
  try {
    return await getServerAuth().middleware({ loginUrl: `/auth/sign-in?redirectTo=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}` })(request);
  } catch {
    return new NextResponse("Sign-in is temporarily unavailable. Please try again shortly.", { status: 503 });
  }
}

export const config = {
  matcher: ["/generate/:path*", "/revoice/:path*", "/evaluation/:path*", "/workspace/:path*", "/profiles/:path*", "/benchmarks/:path*"],
};
