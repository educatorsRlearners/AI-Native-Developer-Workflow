// Vendored client script for the Web Push subscription flow (#9).
// No bundler, no CDN, no framework. Loaded only by chores/settings.html.
//
// On button click: ask for notification permission, and on "granted" subscribe
// through the already-registered service worker (#8) and POST the subscription
// to chores:push-subscribe with the CSRF token. The button always shows exactly
// one state so the current situation can be checked by eye.

(function () {
  "use strict";

  var button = document.getElementById("enable-notifications");
  if (!button) {
    return;
  }

  var SUBSCRIBE_URL = button.dataset.subscribeUrl;
  var VAPID_PUBLIC_KEY = button.dataset.vapidKey;

  function csrfToken() {
    var el = document.querySelector('meta[name="csrf-token"]');
    return el ? el.getAttribute("content") : "";
  }

  // base64url string -> Uint8Array, as pushManager.subscribe expects.
  function urlBase64ToUint8Array(base64String) {
    var padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    var raw = atob(base64);
    var output = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i += 1) {
      output[i] = raw.charCodeAt(i);
    }
    return output;
  }

  function setState(state) {
    button.disabled = true;
    button.dataset.state = state;
    switch (state) {
      case "unsupported":
        button.textContent = "Notifications aren't supported in this browser";
        break;
      case "blocked":
        button.textContent =
          "Notifications are blocked — enable them in browser settings";
        break;
      case "on":
        button.textContent = "Notifications are on for this device";
        break;
      default:
        button.textContent = "Enable notifications";
        button.disabled = false;
    }
  }

  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    setState("unsupported");
    return;
  }

  if (typeof Notification !== "undefined" && Notification.permission === "denied") {
    setState("blocked");
    return;
  }

  // Reflect any subscription this browser already holds.
  navigator.serviceWorker.ready
    .then(function (registration) {
      return registration.pushManager.getSubscription();
    })
    .then(function (subscription) {
      setState(subscription ? "on" : "ready");
    })
    .catch(function () {
      setState("ready");
    });

  function subscribeAndSave() {
    return navigator.serviceWorker.ready
      .then(function (registration) {
        return registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
        });
      })
      .then(function (subscription) {
        return fetch(SUBSCRIBE_URL, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken(),
          },
          body: JSON.stringify(subscription),
        });
      })
      .then(function (response) {
        setState(response && response.ok ? "on" : "ready");
      });
  }

  button.addEventListener("click", function () {
    if (button.disabled) {
      return;
    }
    button.disabled = true;
    Notification.requestPermission()
      .then(function (permission) {
        if (permission === "denied") {
          setState("blocked");
          return undefined;
        }
        if (permission !== "granted") {
          // Prompt dismissed ("default"): quietly return to the ready state.
          setState("ready");
          return undefined;
        }
        return subscribeAndSave();
      })
      .catch(function () {
        setState("ready");
      });
  });
})();
