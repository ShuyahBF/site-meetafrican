// Service worker de beAuthentik (application Android installable via PWABuilder).
// Rôle UNIQUE : quand l'ouverture d'une page échoue faute d'Internet, afficher la page « Pas de connexion »
// (offline.html) au lieu de l'erreur du navigateur. Rien d'autre n'est mis en cache : le site reste toujours à jour.
const CACHE_HORS_LIGNE = "beauthentik-hors-ligne-1";

// Installation : on garde de côté la seule page hors ligne
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE_HORS_LIGNE).then((c) => c.add("/offline.html")).catch(() => {}));
  self.skipWaiting();
});

// Ouverture d'une page (navigation) : réseau d'abord ; en cas d'échec, page hors ligne
self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(
    fetch(event.request).catch(() => caches.match("/offline.html").then((r) => r || Response.error())),
  );
});

// Activation : prise de contrôle immédiate des pages ouvertes
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
