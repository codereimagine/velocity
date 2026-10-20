// velocity offline fallback — keeps the instrument openable with no connection.
// Same-origin only: the speed test (speed.cloudflare.com) and the local agent
// (127.0.0.1:7717) are never intercepted or cached, so a measurement is always live.
var CACHE = "velocity-v1";
var SHELL = ["./", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;   // live traffic: hands off
  if (req.mode === "navigate") {
    // network first, so an update is never stuck behind the cache; the saved page only when offline
    e.respondWith(fetch(req).then(function (res) {
      var copy = res.clone(); caches.open(CACHE).then(function (c) { c.put("./", copy); }); return res;
    }).catch(function () { return caches.match("./"); }));
    return;
  }
  e.respondWith(caches.match(req).then(function (hit) { return hit || fetch(req); }));
});
