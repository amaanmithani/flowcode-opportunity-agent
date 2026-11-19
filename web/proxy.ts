import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Password-protects the whole site, pages and the research API alike, when SITE_PASSWORD is set.
// Uses HTTP Basic auth: the browser asks once and remembers.
// SITE_USERNAME is optional; if it is unset, any username works.
// With SITE_PASSWORD unset (locally, or to make the site public), the site stays open.
export function proxy(request: NextRequest) {
  const password = process.env.SITE_PASSWORD;
  if (!password) return NextResponse.next();
  const username = process.env.SITE_USERNAME;

  const header = request.headers.get("authorization") ?? "";
  if (header.startsWith("Basic ")) {
    try {
      const decoded = atob(header.slice(6));
      const sep = decoded.indexOf(":");
      const suppliedUser = decoded.slice(0, sep);
      const supplied = decoded.slice(sep + 1);
      if (supplied === password && (!username || suppliedUser === username)) return NextResponse.next();
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
