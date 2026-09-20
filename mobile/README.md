# EnergyFox CRM — mobile PWA

A Flutter web app that installs to a phone's home screen and behaves like a
native app: its own icon and splash, no browser chrome, bottom tab bar, pull to
refresh, haptics, and an app-shell service worker so it opens instantly and
survives a dead signal.

It talks to the same Django API as the Next.js web app (`/api/token/`,
`/api/leads/`, `/api/tasks/`, …) — there is no second backend and no second
source of truth.

## What's in it

| Screen | What it does |
| --- | --- |
| **Sign in** | JWT against `/api/token/`, with the CRM server address editable under *Server settings*. Tokens are stored locally and refreshed automatically; only a dead refresh token signs you out. |
| **Top bar** | The hamburger (every other module, with a dot when work is waiting in one), where you are, day/night, the notifications bell with its unread count, and your picture — the same four corners the web app's phone header has. |
| **Menu** | Every module this account may open, filtered by exactly the rules the web sidebar runs on, each with the same "waiting on you" badge. The work queues open in the app; the modules whose paperwork belongs on a big screen open in the browser and say so. |
| **Home** | Live KPIs (total leads, new today, pipeline value, revenue), a six-month revenue chart, the pipeline split by status (tap a status to filter the lead book), the team leaderboard for managers, and the recent activity feed. |
| **Leads** | The lead book, paged as you scroll, filtered by status and by "mine only", searchable across name, phone, place and owner. Tap through to the lead. |
| **Lead** | Header with status and deal value; one tap to place a **CRM call** (`/api/calls/initiate/`, so it is recorded and logged), or to dial, WhatsApp or email directly; change status; add a task; full details; the lead's activity timeline. |
| **Calls** | The call log the web app has on a phone: every call in or out, how it ended, how long it ran and who made it — tap for the lead, or ring straight back. |
| **Tasks** | Tabs for To Do / In Progress / In Review / Done with live counts, overdue flagged in red (and badged on the tab bar), tick to complete, tap to edit, create from anywhere. |
| **Work queues** | Documentation (both stages and the tracker), Warranty, KSEB Feasibility, Accounts and its payment buckets, Completed Projects, Purchase & Logistics, Project and Overdue Projects, Service, Liasoning, Discom Follow-up, Periodic Maintenance, Emergency Service, Converted Leads and Closed Deals — who is waiting, what stands where, and the number to ring about it. |
| **Profile** | Who you are signed in as, light/dark/system, the server address, refresh everything, sign out. |

What an account sees and what it may do are both the server's rules, mirrored:
the modules come from the same list as the web sidebar (`lib/state/nav.dart`),
and every write control is behind the gate of the same name in
`leads/access.py` (`lib/api/models.dart`). A BDE receives leads rather than
sourcing them, so they get no "new lead" button; a spectator ("view only")
account gets every screen and no working button at all; a custom user type gets
exactly the modules and capabilities its role was granted in Settings. The
rules are covered by `test/access_test.dart`.

## Run it in development

```bash
cd mobile
flutter pub get
flutter run -d chrome
```

By default the app points at `http://localhost:8000` when it is running on
localhost, and at its own origin everywhere else. Change it any time under
*Server settings* on the sign-in screen, or *Profile → Server*.

Django must allow the origin the app is served from. In development
`CORS_ALLOW_ALL_ORIGINS` is already on when `DEBUG=1`; in production add the
app's origin to `CORS_ALLOWED_ORIGINS` in `.env`.

## Build and deploy

### Android APK

```bash
./build_apk.sh                             # server is entered on the sign-in screen
./build_apk.sh https://crm.energyfox.co    # that server baked in as the default
```

Output lands in `build/app/outputs/flutter-apk/`: a universal APK (~53 MB) plus
per-ABI ones — `app-arm64-v8a-release.apk` (~19 MB) is the one to hand to
people, it covers every phone sold in the last decade.

They are signed with the debug key, which is fine for sideloading and internal
testing but not for Play. For a store release, add a signing config to
`android/app/build.gradle.kts` and build an app bundle:

```bash
flutter build appbundle --dart-define=API_BASE=https://crm.energyfox.co
```

A packaged app has no page origin to infer the API from, so either bake the
address in with `--dart-define=API_BASE=…` or leave it out and let each person
type it once on the sign-in screen. `android:usesCleartextTraffic` is on, since
the project's default nginx config serves plain HTTP before TLS is enabled —
turn it off in `android/app/src/main/AndroidManifest.xml` once the CRM is on
HTTPS.

### Web PWA

```bash
./build_pwa.sh            # served from the site root
./build_pwa.sh /app/      # served from https://crm.example/app/
```

The output is a static directory, `build/web`. Copy it to the server and serve
it over **HTTPS** — service workers and "Add to home screen" do not work over
plain HTTP (localhost excepted).

Serving it from the CRM's own domain is the simplest deployment: the app then
finds the API on its own origin with nothing to configure. With the project's
nginx in front, add:

```nginx
# The mobile PWA, built with:  ./build_pwa.sh /app/
location /app/ {
    alias /srv/energyfox-pwa/;
    try_files $uri $uri/ /app/index.html;

    # The shell must be re-checked every launch or an update never lands.
    location ~* /app/(index\.html|sw\.js|flutter_bootstrap\.js)$ {
        add_header Cache-Control "no-cache, must-revalidate";
    }
}
```

`/api/` is already proxied to Django by the existing config, so nothing else
changes.

### Installing it

- **Android / Chrome** — the install prompt appears on its own; or ⋮ → *Install app*.
- **iOS / Safari** — Share → *Add to Home Screen*. It then launches full-screen
  with the navy splash and the EnergyFox mark.

## How it is put together

```
lib/
  main.dart              app entry, providers, the signed-in / signed-out gate
  theme.dart             brand colours (sampled from LOGO.png) and both themes
  api/
    api_client.dart      JWT session, one-shot token refresh, error mapping
    models.dart          Lead, TaskItem, AppUser, DashboardStats, DRF paging
  state/
    auth.dart            session, identity, workspace statuses, theme mode
    nav.dart             every module, and who may see it — the web sidebar, ported
    stores.dart          dashboard / leads / calls / tasks / queues / badges / bell
  ui/                    one file per screen, shared pieces in ui/widgets/
    shell.dart           the frame: bottom bar, drawer, the gated create button
    app_drawer.dart      the hamburger — every module this account may open
    module_screen.dart   any work queue, and one customer inside it
web/
  index.html             boot splash, iOS meta, service-worker registration
  manifest.json          name, icons, standalone display, home-screen shortcuts
  sw.js                  app-shell cache — never caches API or media responses
  flutter_bootstrap.js   starts the engine without Flutter's own (no-op) worker
  icons/                 generated from the project's LOGO.png
```

Android lives in `android/`: the launcher icon (including the adaptive one) and
the navy launch screen are generated from the same logo — after changing it run
`dart run flutter_launcher_icons` as well as the `sips` commands below.

Icons and the in-app mark all come from `../LOGO.png`. To refresh them after a
logo change:

```bash
sips -c 734 734 ../LOGO.png --out /tmp/square.png
sips -z 1024 1024 /tmp/square.png --out assets/logo.png
for s in 192 512; do
  sips -z $s $s /tmp/square.png --out web/icons/Icon-$s.png
  cp web/icons/Icon-$s.png web/icons/Icon-maskable-$s.png
done
sips -z 180 180 /tmp/square.png --out web/icons/apple-touch-icon.png
sips -z 32 32 /tmp/square.png --out web/favicon.png
```

## Scope

This is the field app — the parts of the CRM that get used standing in
somebody's yard: leads, calls, statuses, tasks and the numbers. Those four are
the bottom bar, and everything else is behind the hamburger.

The fulfilment modules are **readable** here: each work queue lists its
customers with what stands where and a way to ring them, which is what somebody
away from a desk actually needs from Accounts or Documentation. Filling them in
— uploads, verifications, sign-offs — is still the web app's job, and each
record carries a button through to it. Settings, Automations, Campaigns, Meta,
Branches, Inventory and the performance boards have no phone screen at all and
open in the browser; the menu marks them so nobody taps expecting otherwise.
