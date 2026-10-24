# Creaturist — Prototype PRD
## Product Requirements Document · Web Prototype v0.1

---

## Purpose

Build a mobile-web prototype to validate three things:

1. **Can we show the player on a map with accurate GPS?** — Does the browser's Geolocation API give us good enough position in Prague streets?
2. **Can we show creature pins at real locations and know the player's distance to them?** — Does the distance calculation work reliably at street level?
3. **Can we build a functional proximity tracker?** — When the player walks toward a creature, can we show live distance countdown and direction in real-time?

Everything else is secondary. This is a proof-of-concept, not a product.

---

## Platform

**Mobile web app.** Runs in Safari on iPhone. No app store, no native build, no React Native.

- Single HTML page with embedded JS/CSS (or a simple web server)
- Uses browser Geolocation API for GPS
- Uses a map library (Mapbox GL JS or Leaflet) rendered in the browser
- Hosted locally or on Fly.io (single static site)

**Why browser:**
- No Xcode, no provisioning profiles, no TestFlight
- Open URL on iPhone → test immediately
- Geolocation API works in Safari on iOS (with HTTPS requirement)
- Good enough to validate GPS accuracy and proximity UX

**HTTPS requirement:**
- iOS Safari blocks Geolocation on HTTP. Must serve over HTTPS.
- Options: localhost with a self-signed cert, Fly.io deployment, or ngrok tunnel

---

## Scope

### IN this prototype:
- Map centered on player's live GPS position
- Creature pins at 26 real Prague locations
- Pin tap → creature info with distance
- Proximity tracker overlay (distance + direction) when within 500m
- Encounter screen when within 10m
- Capture (just a button tap + save to localStorage)
- Basic bestiary showing caught/uncaught creatures

### NOT in this prototype:
- Audio (no proximity hum, no capture sound, no narration)
- Haptics (no vibration)
- Quests tab
- Profile / stats
- Onboarding
- Offline support
- Server backend (all data is hardcoded or in a JSON file)
- Authentication
- Polish / animations
- Condition-based spawning (all creatures always visible)
- Any kind of deployment pipeline

---

## Data

All creature data is a static JSON file embedded in the app. No API calls needed for the prototype.

### Spawn points

26 Prague creatures with hardcoded GPS coordinates. Sourced from the Prague Bestiary and Quest Master Script.

```
// Example structure
{
  creatures: [
    {
      id: 34,
      name: "Golem",
      rarity: "Rare",
      badge: "⚗️",
      region: "Prague",
      description: "Clay guardian of Josefov",
      lat: 50.0900,
      lng: 14.4240,
      location_name: "Josefov, Old Jewish Quarter"
    },
    // ... 25 more
  ]
}
```

GPS coordinates come from the Prague Bestiary v2.0 Expanded document. Where exact GPS isn't available (many Prague creatures), use the neighborhood center coordinates:

| Area | Approximate Center |
|---|---|
| Josefov / Old Jewish Quarter | 50.0900, 14.4240 |
| Old Town Square / Celetná | 50.0875, 14.4215 |
| Vyšehrad cliff | 50.0655, 14.4175 |
| Charles Bridge | 50.0865, 14.4115 |
| Kampa / Čertovka | 50.0860, 14.4095 |
| Hradčany / Castle | 50.0910, 14.4000 |
| Žižkov | 50.0830, 14.4520 |
| Karlín | 50.0920, 14.4480 |
| Šárka valley | 50.0820, 14.3500 |
| Děvín ridge | 50.0850, 14.3450 |
| Karlovo náměstí / New Town | 50.0780, 14.4195 |
| Malá Strana | 50.0870, 14.4070 |
| Old Town weir / Vltava | 50.0880, 14.4150 |
| Powder Gate | 50.0874, 14.4280 |
| Dalibor Tower | 50.0915, 14.3990 |
| Nusle Bridge | 50.0677, 14.4326 |

---

## Screens

### Screen 1: Map

**What it is:** Full-viewport map. The whole screen is the map.

**What it shows:**
- Map tiles (street-level detail, dark or standard style)
- Player position: blue dot, auto-centered, follows as player moves
- Creature pins: colored markers at fixed GPS positions
  - Each pin shows the creature's badge emoji as a label
  - Pin color matches rarity: grey, green, teal, blue, purple, gold, red
- Distance rings (optional, helpful for testing):
  - 500m ring (where tracker activates)
  - 200m ring (where audio would start)
  - 10m ring (where encounter triggers)

**Interactions:**
- Tap a creature pin → info panel slides up from bottom
- Info panel shows: creature name, rarity badge, distance from player in meters, location name
- Info panel has a "Track" button → starts proximity tracker for this creature
- Map re-centers on player when they tap a "locate me" button (or auto-follows)

**GPS settings:**
- `enableHighAccuracy: true` — request GPS, not just network location
- `maximumAge: 2000` — accept positions up to 2 seconds old
- `timeout: 10000` — give up after 10 seconds
- Watch position continuously (`watchPosition`) for live tracking

### Screen 2: Proximity Tracker

**What it is:** An overlay that appears when the player activates tracking on a creature (or auto-activates when within 500m).

**What it shows:**
- Semi-transparent overlay on top of the map
- Large distance number in the center: **"247 m"** — updates in real-time as player walks
- Direction arrow pointing toward the creature (compass bearing calculated from player heading + bearing to creature)
- Creature name and rarity at the top
- Color changes based on distance:
  - > 200m: blue/cool tone
  - 200-50m: yellow/warm
  - < 50m: red/hot — plus text "You're very close!"
- "Cancel" button to stop tracking

**How direction works:**
- Calculate bearing from player position to creature position (haversine formula)
- If device supports `DeviceOrientationEvent` (iPhone does): subtract player's phone heading from bearing to get relative direction
- Show an arrow: ↑ (straight ahead), ↗ (slight right), → (right), etc.
- Fallback if no orientation: just show distance and "head roughly NE" text

**When encounter triggers:**
- Distance drops below 10m → tracker auto-transitions to encounter screen

### Screen 3: Encounter

**What it is:** Full-screen card that appears when player is within 10m of a creature.

**What it shows:**
- Creature name, badge, rarity
- Description text
- "Capture" button (big, centered)
- "Not now" link to dismiss

**On capture:**
- Save to localStorage: `{ creature_id, timestamp, lat, lng }`
- Show "Captured!" confirmation for 2 seconds
- Return to map

**On dismiss:**
- Return to map, tracker deactivated for this creature

### Screen 4: Bestiary

**What it is:** Simple list/grid of all 26 creatures.

**What it shows:**
- Each creature: badge + name + rarity
- Caught creatures: full color, shows capture date
- Uncaught creatures: greyed out, dimmed

**Accessed from:** A small book icon button in the top-right corner of the map screen.

---

## Technical Implementation

### Stack
- **HTML + CSS + vanilla JavaScript** (or a tiny framework like Preact if preferred)
- **Mapbox GL JS** for the map (free tier: 50K loads/month, plenty for testing)
  - Alternative: **Leaflet + OpenStreetMap** (completely free, no API key)
- **Geolocation API** for GPS (`navigator.geolocation.watchPosition`)
- **DeviceOrientationEvent** for compass heading (iPhone Safari supports this)
- **localStorage** for captures

### File structure
```
prototype/
├── index.html          ← single page app
├── app.js              ← all logic
├── style.css           ← styling
└── data.js             ← creature spawn points JSON
```

No build step. No bundler. Open index.html or serve with any static server.

### Key functions to implement

```javascript
// GPS
startWatchingPosition()     → navigator.geolocation.watchPosition(...)
getCurrentPosition()         → navigator.geolocation.getCurrentPosition(...)

// Distance & direction
distanceBetween(lat1, lng1, lat2, lng2)     → haversine formula, returns meters
bearingTo(lat1, lng1, lat2, lng2)            → returns degrees
relativeBearing(heading, bearing)            → phone heading → relative direction

// Map
initMap()                    → create Mapbox/Leaflet map
updatePlayerPosition(lat, lng)
addCreaturePin(creature)
updateDistanceToCreatures()

// Tracker
startTracking(creatureId)
stopTracking()
updateTrackerUI(distance, bearing)

// Encounters
checkProximity()             → called on every GPS update
triggerEncounter(creature)
captureCreature(creatureId)

// Bestiary
loadCaptures()               → from localStorage
saveCapture(creatureId, data)
renderBestiary()
```

### GPS accuracy considerations

- iPhone GPS in urban Prague: typically 5-15m accuracy outdoors
- `enableHighAccuracy: true` is critical — without it, iPhone uses cell tower triangulation (100m+ error)
- The 10m encounter trigger should account for GPS accuracy: trigger when `distance < max(10, accuracy * 1.5)`
- Show GPS accuracy on screen during testing (helpful for debugging)
- GPS may be poor indoors or in narrow streets between tall buildings — expect this, log it

### HTTPS requirement

iOS Safari requires HTTPS for Geolocation API. Options for testing:

1. **ngrok** — tunnel localhost to a public HTTPS URL (`ngrok http 8080`)
2. **Fly.io** — deploy as a static site (`fly deploy`)
3. **Self-signed cert** — painful on iOS, not recommended
4. **localhost exception** — Safari allows Geolocation on `localhost` without HTTPS. Use this for initial dev.

---

## Testing Plan

### Test 1: GPS accuracy
- Walk around a known Prague location (e.g. Old Town Square)
- Does the blue dot follow you accurately?
- How much jitter? (log accuracy values)
- Does it work in narrow streets? Between buildings?

### Test 2: Distance calculation
- Stand at a known creature location (e.g. Charles Bridge)
- Does the distance to the Bruncvík pin read ~0m?
- Walk 100m away — does it read ~100m?
- Walk 500m away — does it read ~500m?

### Test 3: Proximity tracker
- Start tracking a creature 300m away
- Walk toward it
- Does the distance count down smoothly?
- Does the direction arrow point the right way?
- Does the encounter trigger when you arrive?

### Test 4: Capture flow
- Walk to a creature location
- Encounter screen appears
- Tap Capture
- Check bestiary — creature is marked as caught
- Refresh page — capture persists (localStorage)

### Test 5: Multiple creatures
- Stand somewhere with 3+ creatures within 2km (e.g. near Old Town)
- Do all pins appear?
- Can you track one while others are visible?

---

## Success Criteria

The prototype succeeds if:

1. ✅ GPS position is accurate to within 15m outdoors in Prague
2. ✅ Distance to creature pins calculates correctly (±5m at close range)
3. ✅ Proximity tracker shows live distance that counts down as you walk
4. ✅ Direction arrow is approximately correct (±30°)
5. ✅ Encounter triggers reliably when standing at a creature's location
6. ✅ Capture saves and persists across page refreshes

If these work, we know the core GPS + proximity mechanic is viable and we can build the full app on top of it.

---

## Delivery

- Deploy to a URL (ngrok or Fly.io)
- Open on iPhone Safari
- Walk to Old Town Prague and test
- Report: GPS accuracy log, screenshot of tracker working, any issues

Time estimate: 1-2 days of dev work for an experienced JavaScript developer.
