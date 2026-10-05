/* Mavis service worker: installability, and a scope for future push.
 *
 * This deliberately caches nothing. The dashboard is live paper-trading state --
 * a cached shell would show stale signals, stale P&L and a scanner that looks
 * frozen. The worker exists so the app installs to the home screen and opens
 * standalone, which is what makes it a phone app rather than a bookmark.
 */
self.addEventListener("install", (event) => event.waitUntil(self.skipWaiting()));
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
