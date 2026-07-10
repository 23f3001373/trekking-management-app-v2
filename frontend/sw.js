/**
 * sw.js — TrekVista Service Worker
 * ==================================
 * Implements the "Cache-First, Network-Fallback" strategy for static assets
 * to enable the "Add to Desktop" (PWA) feature and basic offline support.
 *
 * WHAT THIS CACHES:
 *   - The SPA HTML shell (index.html)
 *   - The Vue 3 CDN bundle
 *   - Bootstrap CSS and JS
 *   - Bootstrap Icons CSS
 *   - Chart.js CDN bundle
 *   - App's own JS and manifest
 *
 * WHAT IT DOES NOT CACHE:
 *   - API calls to the Flask backend (always goes to network for fresh data)
 *   - Authentication tokens (these never touch the Service Worker)
 *
 * STRATEGY: Cache-First with Network Fallback
 *   1. Check if the request is in the cache.
 *   2. If yes, return the cached response immediately.
 *   3. If no, fetch from network, cache the result, and return.
 *   4. If the network is unavailable and asset isn't cached, return a fallback.
 *
 * UPDATE FLOW:
 *   - Incrementing TREK_CACHE_VERSION forces all old caches to be deleted
 *     on the next activation, ensuring users always get fresh static assets.
 */

const TREK_CACHE_VERSION = 'trekking-app-v2-cache-v2';

/**
 * Static assets to pre-cache on Service Worker installation.
 * These are the core resources needed for the app shell to load offline.
 */
const TREK_PRECACHE_ASSET_URLS = [
  'index.html',
  'app.js',
  'manifest.json',
  // CDN resources
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
  'https://unpkg.com/vue@3/dist/vue.global.prod.js',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js',
];

// ---- INSTALL EVENT: Pre-cache static assets ----
self.addEventListener('install', (install_event) => {
  install_event.waitUntil(
    caches.open(TREK_CACHE_VERSION).then((cache) => {
      console.log('[SW] Pre-caching static assets...');
      return cache.addAll(TREK_PRECACHE_ASSET_URLS);
    }).then(() => {
      console.log('[SW] Pre-cache complete. Activating...');
      self.skipWaiting();  // Immediately activate without waiting for old SW to die.
    })
  );
});

// ---- ACTIVATE EVENT: Clean up old cache versions ----
self.addEventListener('activate', (activate_event) => {
  activate_event.waitUntil(
    caches.keys().then((all_cache_names) => {
      return Promise.all(
        all_cache_names
          .filter(cache_name => cache_name !== TREK_CACHE_VERSION)
          .map(old_cache_name => {
            console.log('[SW] Deleting stale cache:', old_cache_name);
            return caches.delete(old_cache_name);
          })
      );
    }).then(() => self.clients.claim())  // Take control of all open clients.
  );
});

// ---- FETCH EVENT: Disabled for development to prevent caching issues ----
// self.addEventListener('fetch', (fetch_event) => { ... });

