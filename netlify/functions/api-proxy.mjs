// Same-origin API relay for the Google Cloud backend.
// The browser supplies the operator token; this function forwards it without
// storing it in Netlify or exposing it in a URL.
export default async (request) => {
  const backend = String(Netlify.env.get("MULTIBOT2_BACKEND_URL") || "").trim().replace(/\\/+$/, "");
  if (!backend || !/^https:\\/\\//i.test(backend)) {
    return Response.json(
      { ok: false, error: "Secure backend URL is not configured.", code: "BACKEND_NOT_CONFIGURED" },
      { status: 503, headers: { "cache-control": "no-store" } }
    );
  }

  const incomingUrl = new URL(request.url);
  const path = incomingUrl.pathname;
  const allowed = new Set([
    "/api/dashboard", "/api/health", "/api/diagnostics/sweep",
    "/api/settings", "/api/notifications", "/api/calendar",
    "/api/news", "/api/backtest"
  ]);
  if (!allowed.has(path)) {
    return Response.json(
      { ok: false, error: "Unknown API route.", code: "NOT_FOUND" },
      { status: 404, headers: { "cache-control": "no-store" } }
    );
  }

  const headers = new Headers({
    "accept": request.headers.get("accept") || "application/json",
    "x-forwarded-host": incomingUrl.host
  });
  for (const name of ["origin", "referer", "content-type", "x-admin-token", "authorization"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const upstream = await fetch(backend + path + incomingUrl.search, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method.toUpperCase()) ? undefined : await request.arrayBuffer(),
      redirect: "manual"
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") || "application/json",
        "cache-control": upstream.headers.get("cache-control") || "no-store"
      }
    });
  } catch {
    return Response.json(
      { ok: false, error: "Backend connection failed.", code: "BACKEND_UNAVAILABLE" },
      { status: 502, headers: { "cache-control": "no-store" } }
    );
  }
};

export const config = { path: "/api/*" };
