import { NextResponse, type NextRequest } from "next/server";

import { getServerAuth, serverAuthConfigured } from "@/lib/auth/server";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path: string[] }> };

function privateResponse(response: Response): Response {
  response.headers.set("Cache-Control", "private, no-store, max-age=0");
  return response;
}

export async function GET(request: NextRequest, context: RouteContext) {
  if (!serverAuthConfigured()) return NextResponse.json({ error: "Authentication is not configured." }, { status: 503 });
  return privateResponse(await getServerAuth().handler().GET(request, context));
}

export async function POST(request: NextRequest, context: RouteContext) {
  if (!serverAuthConfigured()) return NextResponse.json({ error: "Authentication is not configured." }, { status: 503 });
  return privateResponse(await getServerAuth().handler().POST(request, context));
}
