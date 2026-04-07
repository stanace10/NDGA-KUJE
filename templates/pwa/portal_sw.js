const NDGA_CACHE = "ndga-learning-cache-v1";
const OFFLINE_ROUTES = [
  "/portal/student/learning-hub/",
  "/portal/student/lms/",
  "/portal/student/weekly-challenge/",
  "/static/css/styles.css",
  "/static/js/portal-sw-register.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(NDGA_CACHE).then((cache) => cache.addAll(OFFLINE_ROUTES)).catch(() => null)
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== NDGA_CACHE)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }

  const requestUrl = new URL(event.request.url);
  const isLearningPage =
    requestUrl.pathname.startsWith("/portal/student/learning-hub/") ||
    requestUrl.pathname.startsWith("/portal/student/lms/") ||
    requestUrl.pathname.startsWith("/portal/student/weekly-challenge/") ||
    requestUrl.pathname.startsWith("/media/learning/");

  if (!isLearningPage) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const cloned = response.clone();
        caches.open(NDGA_CACHE).then((cache) => cache.put(event.request, cloned));
        return response;
      })
      .catch(() =>
        caches.match(event.request).then((cached) => cached || caches.match("/portal/student/lms/"))
      )
  );
});
