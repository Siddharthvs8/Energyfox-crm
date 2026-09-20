// Flutter's own generated service worker no longer caches anything — it
// unregisters itself on activate. The app ships its own `sw.js` instead (see
// index.html), so the loader is started here without service-worker settings,
// which keeps Flutter from registering a worker that would fight with ours.
{{flutter_js}}
{{flutter_build_config}}

_flutter.loader.load();
