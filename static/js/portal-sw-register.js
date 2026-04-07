(function () {
  if (!("serviceWorker" in navigator)) {
    return;
  }
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/portal-sw.js").catch(function () {
      return null;
    });
  });
})();
