# Creaturist — MVP App Design

## What are we building

A mobile app where you walk around Prague and collect creatures from Czech folklore. You open it, see a map with creatures near you, walk to one, and capture it. Like Pokémon GO but with Czech myths, audio-first encounters, and real Prague locations.

The MVP is Prague-only, 26 creatures, condition-based capture (no microphone/gestures yet), and enough of a game loop to be playable and testable.

---

## The Core Loop

```
Open app → See map with creatures nearby → Pick one → Walk there
→ Proximity tracker shows direction + distance → Get close
→ Encounter screen → Capture (if conditions met) → Points + collection update
→ Check bestiary → Pick next creature → Repeat
```

---

## Screens

### 1. Map (Home Screen)

The default screen. Full-screen map centered on the player.

**What you see:**
- Player dot with heading arrow
- Creature pins scattered around Prague at real locations
- Each pin shows the creature's rarity color
- Bottom tab bar: Map · Bestiary · Quests · Profile

**Interactions:**
- Tap a pin → bottom sheet appears with creature name, rarity, distance, and a "Go" button
- "Go" opens walking directions (system maps or in-app compass mode)
- Pins pulse gently when you're within 500m
- Only shows creatures within ~2km to keep it clean

**Pin behavior:**
- Caught creatures show their badge emoji on the pin
- Uncaught creatures show a mystery/silhouette pin
- Some pins only appear at certain times (night-only, dawn-only creatures)

### 2. Proximity Tracker

Activates automatically when you walk within 500m of a creature. Not a separate screen — it's an overlay on the map.

**What you see:**
- Screen border pulses with the creature's rarity color
- Large distance number counting down (487m... 412m... 298m...)
- Compass arrow pointing toward the creature
- Creature name and rarity at the top

**Feedback layers:**
- 500-200m: slow pulse, faint hum
- 200-50m: faster pulse, hum gets louder, haptic tap every 50m
- 50-10m: rapid pulse, "Very close" text, continuous gentle buzz
- <10m: encounter triggers

**If you walk away past 600m:** tracker fades out, "Creature lost" toast

### 3. Encounter / Capture

Full-screen takeover when you're within 10m of the spawn point.

**What you see:**
- Creature illustration (placeholder art for MVP)
- Atmospheric background matching the location (dark street, river, castle wall, forest)
- Creature name and rarity

**Capture logic (MVP — no active input):**
- App checks spawn conditions: time of day, night/day, event calendar
- If conditions met → automatic capture after 2 seconds
- If conditions not met → "The creature is not here right now" with a hint about when to return

**On successful capture:**
- 2-second capture animation (creature compresses into phone)
- Haptic: pulse → pulse → ping
- Points added (10-600 based on rarity)
- 3 seconds of silence
- If audio file exists for this creature → plays narration
- "Added to collection" confirmation

### 4. Bestiary

Grid of all 153 creatures. The Pokédex.

**Layout:**
- 4-column grid, each cell is a creature card
- Caught: full color, badge, name, tap for details
- Uncaught: dark silhouette, "???", rarity border color visible
- Top bar: "27 / 153" counter
- Filter tabs: All · Caught · By Rarity · By Region
- Search bar

**Tap a caught creature → Detail screen:**
- Large illustration
- Name, ID badge, rarity tier, region
- Flavor text description
- "Hear Story" button (plays audio if available)
- Date and location of capture
- Which quest it belongs to

**Tap an uncaught creature → greyed card:**
- Rarity tier visible
- Region visible
- Everything else hidden

### 5. Quests

List of the 8 Prague quest lines. Each quest is a themed walking route.

**Layout:**
- Card per quest: title, location, creature count, progress (1/3 caught)
- Tap → quest detail: list of creatures in this quest, which you've caught, which remain
- Completed quests show a checkmark and completion date

**Quests don't do anything functional in MVP** — they're a progress tracker and a suggested walking route. No quest-gating of creatures.

### 6. Profile

Simple stats screen.

- Player name (auto-generated, editable)
- Total points
- Creatures caught / total
- Quests completed
- Distance walked
- Time played
- Settings: sound on/off, haptics on/off, map style

---

## How Spawning Works (MVP)

Every Prague creature has a **fixed real-world location**. No random spawns. No migration. The Golem is always in Josefov. Libuše is always at Vyšehrad.

**When a pin appears on the map:**
1. App checks player's GPS position
2. Fetches all spawn points within 2km
3. For each spawn point, checks if conditions are currently met:
   - Time of day (night-only creatures hide during the day)
   - Seasonal (Mikuláš Čert only shows Dec 5)
   - Always-active creatures always show
4. Pins that pass the check appear on the map

**Condition types in MVP:**
- `always` — visible 24/7
- `night` — visible only after sunset
- `dawn` — visible only 30min before/after sunrise
- `seasonal` — visible on specific dates

**Proximity triggers:**
- Pin visible on map: within 2km
- Tracker overlay activates: within 500m
- Audio begins: within 200m
- "Very close": within 50m
- Encounter triggers: within 10m

---

## Technical Stack

### Frontend
- **React Native via Expo** — single codebase, iOS + Android
- **MapBox GL** for the map (free tier covers MVP)
- **Expo Location** for GPS
- **React Navigation** for tabs and screens
- **Expo AV** for audio playback
- **Expo Haptics** for vibration patterns
- **SQLite** (expo-sqlite) for local cache

### Backend
- **Encyclist API** on Fly.io — already deployed, already has all creature data
- Need to add: REST endpoints (mobile can't speak MCP protocol)
- Need to add: spawn points table (creature_id + lat/lng + conditions)
- Need to add: player captures table
- Need to add: audio file serving (static files on Fly.io volume or CDN)

### API endpoints to build:
```
GET  /api/creatures          → all 153 creatures
GET  /api/creatures/:id      → single creature detail
GET  /api/spawns?lat=&lng=   → spawn points near a location
POST /api/captures           → record a capture
GET  /api/player/:id         → player stats
GET  /api/quests             → 8 Prague quests
```

### Auth (MVP)
No auth. Device UUID as player ID. Everything cached locally. Optional cloud sync post-launch.

### Offline
- Map tiles cached via MapBox
- Creature data cached in local SQLite
- Captures queued locally, synced when back online
- Game fully playable offline (GPS + cached data)

---

## Audio (MVP — simplified)

Not the full binaural system. That's post-launch. For MVP:

- **Map ambient:** nothing (silence, or optional city sounds)
- **Proximity hum:** single low-frequency track that fades in from 200m, gets louder as you approach
- **Creature encounter:** 30-second ambient loop per creature archetype (forest, water, urban, castle, underground) — NOT per creature
- **Capture sound:** one universal 2-second "seal" sound (brand identity)
- **Post-capture narration:** pre-recorded audio files if available, otherwise silence

Audio files needed: 5 archetype ambients + 1 universal seal + 1 trophy ping = 7 files total.

---

## What's Post-Launch (NOT building now)

- Active capture mechanics (chanting, listening test, patience hunt, chase)
- Binaural spatial audio with head tracking
- AI-powered Storyteller narration (ElevenLabs + GPT-4o)
- Group encounters
- Multi-visit creatures
- Weather API integration
- Bohemian Switzerland expansion
- Community submissions
- Social features (friends, trading, leaderboards)
- Subscription / monetization
- Proper auth and cloud sync

---

## What to Build First (Dev Order)

1. **Expo project scaffold** — tabs, navigation, hello world map
2. **Map screen** — player location, map rendering
3. **Spawn points API** — add REST endpoint + seed Prague locations
4. **Creature pins on map** — fetch spawns, render pins
5. **Pin tap → bottom sheet** — creature info + distance
6. **Proximity tracker** — distance calc, direction arrow, pulsing UI
7. **Encounter screen** — trigger at <10m, condition check
8. **Capture flow** — animation, points, save to local DB
9. **Bestiary** — grid, caught/uncaught, detail screen
10. **Audio** — proximity hum, capture sound, ambient loops
11. **Quests tab** — progress tracker
12. **Profile tab** — stats
13. **Polish** — onboarding, haptics, animations, edge cases

---

*This is a buildable spec. All creature data lives in Encyclist. The app is a thin client that reads from the API, tracks GPS, and manages local state.*
