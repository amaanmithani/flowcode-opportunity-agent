import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Password-protects the whole site, pages and the research API alike, when SITE_PASSWORD is set.
// Uses HTTP Basic auth: the browser asks once and remembers. Any username works.
// Locally, with SITE_PASSWORD unset, the site stays open.
export function proxy(request: NextRequest) {
  const password = process.env.SITE_PASSWORD;
  if (!password) return NextResponse.next();

  const header = request.headers.get("authorization") ?? "";
  if (header.startsWith("Basic ")) {
    try {
      const decoded = atob(header.slice(6));
      const supplied = decoded.slice(decoded.indexOf(":") + 1);
      if (supplied === password) return NextResponse.next();
    } catch {
      /* malformed header: fall through to the challenge */
    }
  }
  return new NextResponse("Password required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Flowcode Opportunity Agent", charset="UTF-8"' },
  });
}

export const config = {
  // Everything except Next's static assets.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
