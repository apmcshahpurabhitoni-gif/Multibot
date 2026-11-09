"use strict";

// Same-origin API relay. The operator's X-Admin-Token is forwarded server-side
// to the Google Cloud backend; it is never embedded in frontend code or URLs.
// Configure MULTIBOT2_BACKEND_URL as an HTTPS origin before enabling production use.
exports.handler = async (event) => {
  const backend = String(process.env.MULTIBOT2_BACKEND_URL || "").trim().replace(/\/+$/, "");
  if (!backend || !/^https:\/\//i.test(backend)) {
    return { statusCode: 503, headers: { "content-type": "application/json", "cache-control": "no-store" },
      body: JSON.stringify({ ok: false, error: "Secure backend URL is not configured.", code: "BACKEND_NOT_CONFIGURED" }) };
  }

  const allowed = new Set(["/api/dashboard", "/api/health", "/api/diagnostics/sweep",
    "/api/settings", "/api/notifications", "/api/calendar", "/api/news", "/api/backtest"]);
  const originalPath = String(event.path || "");
  const path = originalPath.startsWith("/api/") ? originalPath : "";
  if (!allowed.has(path)) {
    return { statusCode: 404, headers: { "content-type": "application/json", "cache-control": "no-store" },
      body: JSON.stringify({ ok: false, error: "Unknown API route.", code: "NOT_FOUND" }) };
  }

  const incoming = event.headers || {};
  const host = incoming.host || incoming.Host || "";
  const headers = {
    "accept": incoming.accept || "application/json",
    "x-forwarded-host": host
  };
  if (incoming.origin) headers.origin = incoming.origin;
  if (incoming.referer) headers.referer = incoming.referer;
  if (incoming["content-type"]) headers["content-type"] = incoming["content-type"];
  if (incoming["x-admin-token"]) headers["x-admin-token"] = incoming["x-admin-token"];
  if (incoming.authorization) headers.authorization = incoming.authorization;

  const query = event.rawQuery ? "?" + event.rawQuery : "";
  const method = String(event.httpMethod || "GET").toUpperCase();
  const options = { method, headers, redirect: "manual" };
  if (!["GET", "HEAD"].includes(method) && event.body) {
    options.body = event.isBase64Encoded ? Buffer.from(event.body, "base64") : event.body;
  }

  try {
    const upstream = await fetch(backend + path + query, options);
    const body = await upstream.text();
    return {
      statusCode: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") || "application/json",
        "cache-control": upstream.headers.get("cache-control") || "no-store"
      },
      body
    };
  } catch (error) {
    return { statusCode: 502, headers: { "content-type": "application/json", "cache-control": "no-store" },
      body: JSON.stringify({ ok: false, error: "Backend connection failed.", code: "BACKEND_UNAVAILABLE" }) };
  }
};
