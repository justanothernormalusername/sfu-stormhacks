# Task Dungeon — Project Brief

**Purpose of this document:** a self-contained handoff brief for brainstorming with an AI model outside this codebase. It describes what Task Dungeon is, what has actually been built and verified, what is deliberately not built, known weaknesses, and directions for expansion. It is written to be read without access to the repository.

**Status:** working prototype, built by one person with AI assistance over roughly one working session. Backend fully tested; game client verified in a real browser via automated Playwright interaction. Not deployed. Not committed to git.

> ## ⚠️ v2 revision — sections 3 through 7 describe v1, which is what is currently built
>
> On **2026-10-04** the owner reviewed this brief and revised the design. **Where this document conflicts with the v2 decision record in §0, §0 wins.** Sections 3–7 are retained as an accurate description of the *existing* code, not as a description of the intended product. Specific retirements are marked inline.
>
> **Status labels used in §0:** **DECIDED** (owner stated or agreed), **LEANING** (floated, direction likely, details open), **PROPOSED** (advisor-raised, not owner-confirmed — a recommendation to discuss, not a requirement), **UNDECIDED** (deferred or never discussed).

---

## 0. The v2 design decision record (2026-10-04)

This is the current design. It supersedes the v1 concept in §1 and the v1 feature set in §3.

### 0.1 The core change

v1 made tasks a **gate**: every task was a room with a locked door that opened when the task was done. v2 replaces this with tasks as **preparation**. The dungeon is a straight sequence: defeating a room's enemy opens the door to the next room. Enemies are tuned to be hard enough that the player cannot get through tough spots without preparing.

Completing real-life tasks — now called **quests** — earns **items, mainly potions**, which go into the player's inventory and are carried into the next battle. The owner's own example: *sleep early → +5 health potions in your inventory before the boss fight.* The loop is **prepare in real life, then fight**.

`completion_in_period` is **DECIDED: kept, repurpose**d. It was "is the door open?" and is now the basis for "what has the player earned this period?" It must remain the single authority, so the displayed state and the enforced state cannot disagree.

### 0.2 Feature verdict table

| v1 feature | Verdict | Notes |
|---|---|---|
| **Locked rooms / unlock rule** | **DECIDED: combat progression** | Tasks do not unlock rooms. Defeating an enemy opens the next room in the line. |
| `completion_in_period` | **DECIDED: keep, repurpose** | Now the basis for period earnings, not door state. |
| **XP system** (10/50/200 XP, level formula, `RoomClear.xp`, HUD bars) | **DECIDED: drop for now** | Owner sees no point in XP currently. May return later. Player attack formerly depended on level, so combat stat sourcing needs a new answer (§0.7 Q7). |
| **Leaderboard** (weekly XP) | **DECIDED: change** | Should track **progress through the level** rather than XP. Definition undecided (§0.7 Q1). |
| **Health bonus** (+5 for any completion in 7 days) | **DECIDED: drop** | Not thought through; may reintroduce later. |
| **Health penalty** (−10 per missed daily in last 7 days) | **UNDECIDED** | Never addressed. Decide whether it survives, since potions now cover healing. **Do not remove or keep it silently — ask.** |
| **Enemy design** (tiers, seeded by task ID) | **UNDECIDED** | New requirement: fights hard without prep, winnable with it. Existing tier/seed structure can stand until redesigned. |
| **Loot** (60% drop, flat attack/defense) | **UNDECIDED** | Potions are now the primary item economy. Keep, merge, or drop the old table is open. |
| **"Loss is never punished"** (§2.4) | **DECIDED: drop this pillar** | Losing should have a setback, e.g. returning to the last checkpoint. Exact penalty UNDECIDED. Keep any setback **mild** — v1 chose no punishment for wellbeing-app churn reasons, so a checkpoint, not stat or progress destruction. |
| **Append-only log + friends flagging** | **DECIDED: keep** | Owner called it a good idea. Must survive any weekly reset. |
| **Turn-based Battle scene** | **DECIDED: keep for now** | Owner first assumed the game was real-time (Soul Knight / Binding of Isaac), then chose turn-based, Pokémon/Undertale-style. Real-time was explicitly *not* chosen; a rewrite would cost more than the available time. |
| **Server-authoritative, derived-not-stored, append-only, timezone correctness** (§2.1–2.3, 2.5) | **DECIDED: preserve** | The new design must not introduce mutable counters. |

**v1 weaknesses made obsolete or changed.** §5.1 (enemy scaling by level) and §5.2 (reward curve) are obsolete as written, because there are no levels or XP. They are replaced by a balance problem: tune enemies against "player with full potions" versus "player with none." §5.3 (placeholder art), §5.4 (accessibility), and §5.8 (onboarding) remain open. §5.6 (no day-7 retention) is partly addressed by the weekly reset and the prepare-then-fight loop.

### 0.3 Quests, potions, and items

- Tasks are **quests**. Completing one grants items the player carries into battle.
- **Items never expire** (DECIDED).
- **Weekly dungeon reset** — **LEANING, not confirmed.** The dungeon resets roughly once a week so items are not held long. The owner said "maybe once a week," so confirm before building. Effect: available = earned *this week* − used *this week*, which acts as a natural cap, since a daily task can pay out at most seven times per week. The log must remain append-only across resets. The week boundary must use the player's local timezone (`APP_TZ`) like the day and month boundaries. **Week start day is UNDECIDED.**
- **Potion categories.** The owner named three: **heal**, **damage boost**, and an **attack speed** effect (citing Soul Knight and Binding of Isaac). **Attack speed does not exist in turn-based combat** — proposed stand-in is *haste* = an extra action this turn, or the enemy skips a turn. Also discussed: **shield** (block the next hit or reduce damage for N turns) and **cleanse/utility** (remove a status, or reveal the enemy's next move).
- **Best idea worth borrowing from Isaac:** items that change *how* combat works, not just add numbers. This is the strongest design idea in the v2 record and should drive the item table.
- **Two dimensions on a reward (PROPOSED):** task *kind* (daily/monthly/goal) sets quantity or potency; *category* (heal/damage/haste/shield/utility) sets the type. This implies a new category attribute on tasks. Decide whether the player can ever override it.

### 0.4 Data model implications

To be designed, not prescribed — but these are the constraints.

- **Potion earning is derived** from completion rows within the current weekly window. No `potions` counter column — this is the §2.2 pillar.
- **Potion use needs its own append-only table**, linked to the battle or user, so `available = earned − used` stays derivable. Design this carefully against the derived-not-stored pillar.
- Tasks likely gain a **category** field, and possibly a cached classifier confidence.
- `RoomClear.xp` and XP code paths go away if XP is dropped. `RoomClear` may still be useful for the leaderboard (§0.7 Q1).
- **No migrations exist.** Any schema change means deleting the local SQLite database. Warn the owner first.
- **API surfaces that change:** `/api/player` (no level/XP), `/api/rooms` (no `unlocked` gating), `/api/rooms/{id}/clear` (the 403 "task not completed" rule disappears), `/api/leaderboard` (progress, not XP). A new endpoint is needed for potion inventory and potion use.
- **Combat currently resolves client-side.** Server-authoritative combat refereeing is feasible now that combat is turn-based, but it is a larger change and is **UNDECIDED**. At minimum, potion counts and progress must be validated server-side.

### 0.5 AI-assisted reward category (BUILT)

The owner wants a model called **Jev** to decide reward and category, with items modeled after *task type* so playstyles complement lifestyles — fitness tasks lead to one item family, sleep tasks to another.

*What Jev is — VERIFIED 2026-10-04 by calling it:* a non-generative decision/classifier model, served through Hack Club's proxy at `https://ai.hackclub.com/proxy/v1/jev/systemone`, model id **`jev-latest`** (resolved to `jev-1.13.0` on the call). It is not a chat model and does not write text. You post a `state` plus a set of named `questions`, each with a type — we use **`choice`**, one of its primitives alongside `score` and `noul` (a yes/no probability). Because the developer defines the possible outputs, it cannot invent categories. Answers come back under `answers.<question_name>`, carrying `choice`, `confidence`, and `probabilities` over every option.

**Access confirmed — the waitlist caveat no longer applies.** The earlier version of this section was written from a web search alone and guessed at TypeSafe AI, a 2026-09-15 launch date, and waitlist-only access; none of that was right. There is no public documentation for the endpoint. The response shape above is from an observed response, not from docs.

Advisor recommendations (**PROPOSED**):
1. **The model picks the category only.** Quantity and potency come from deterministic server code keyed on task kind, so a user cannot create "drink water" worth 50 potions. This preserves server authority.
2. **Classify once at task creation and cache the result on the task row** — never in the gameplay request path.
3. **Build a non-AI fallback first** (keyword rules, or the player picks a category), then layer Jev on top. The demo must not fail on a network error or a missing key.
4. **Use confidence for fallback:** low confidence means default category or ask the player.
5. Jev generates no text, so flavour text (monster names, taunts — §7.7) would still need an LLM or static content.

### 0.6 Balance setup (owner's explicit request)

The owner's teammates will do the balancing and are excited about it. The owner wants the code **ready for that, not balanced yet.** The advisor asked which numbers should be adjustable; **the owner has not answered.**

Proposed approach (**PROPOSED**): gather every tunable into **one config location** — potion amounts by task kind, potion effect strengths and durations, enemy HP/attack per tier, player base stats, damage variance and crit, cooldowns, weekly cap, checkpoint behaviour — and remove magic numbers scattered through the game code and client. How player combat stats are derived now that levels are gone is **UNDECIDED**.

### 0.7 Open questions (UNDECIDED — ask before building)

The ones blocking the first step are **health, leaderboard, and stat source**.

1. **Leaderboard definition.** With a weekly reset, does "furthest room" mean best-ever, this-week, or per-run? How is progress made derivable and tamper-proof?
2. **Loss setback.** Last checkpoint? What defines a checkpoint? Anything else lost?
3. **Health.** Does the missed-daily penalty stay? How does player HP carry between battles now that potions heal?
4. **Carry cap.** Is there a maximum potion count, or does the weekly reset serve as the cap?
5. **Who picks the category.** The game via Jev or fallback rules, the player, or both with an override?
6. **Week start day**, and whether the reset is hard (everything clears) or soft.
7. **Player stat source** without levels.
8. **Loot.** Keep the old drop table, merge it with the potion system, or drop it?
9. **Enemy design.** Roster, tiers, and difficulty targets for "hard without prep, winnable with it."
10. **Server-refereed combat.** In scope or not?
11. **XP.** Fully removed, or hidden behind a flag for a later return?

### 0.8 Suggested order of work (PROPOSED)

Never explicitly ratified by the owner.

1. Ask the blocking questions in §0.7.
2. **Plan before editing** — list what to remove (gating, XP) versus repurpose (`completion_in_period`).
3. Centralize tunables into one config (§0.6) so teammates can start balancing.
4. Remove task-based gates. Rooms unlock in sequence when the previous enemy is defeated.
5. Add potion earning and use as derived records, with deterministic quantities by task kind and a non-AI default category.
6. Wire potions into the Battle scene — heal and damage boost first, then haste and shield.
7. Implement the weekly window in local time.
8. Rework the leaderboard once Q1 is decided.
9. Add the checkpoint setback once Q2 is decided.
10. Add Jev classification **only after** the fallback works and the owner has access.
11. **Deploy a minimal build early, in parallel with all of the above** (see §9).

### 0.9 Settled versus not — quick reference

**Settled:** tasks are preparation instead of gates; enemies open the next room when defeated; potions are the main reward; items don't expire; XP dropped for now; health bonus dropped; loss has a setback; the log is kept; combat stays turn-based; the leaderboard moves to progress; core pillars preserved; code should be balance-ready.

**Leaning:** weekly reset; Jev for category with task-type-themed item families.

**Open:** everything in §0.7, plus the domain idea (§8.1) and the deployment plan (§9).

### 0.10 A note on collaboration

The owner is building this project partly to learn. Prefer proposing a short plan and explaining the reasoning before large rewrites. Do not silently re-implement things beyond what is decided above.

---

## 1. The concept (v1 — superseded by §0.1)

Task Dungeon is a web application that converts a real-life task list into a top-down 2D RPG dungeon.

**The v1 core conceit, now retired:** every task became a room, and the door was locked until the task was completed. In v2 the doors are gone — see §0.1.

The framing that survives the revision is that the dungeon is *literally powered by the player's real-world behaviour* — not "gamified" in the sense of adding badges to a checkbox list. Progress comes entirely from the player acting outside the application. In v2 this shows up as potions earned from real tasks and carried into battle, rather than as doors that swing open.

**Target setting:** SFU StormHacks, a 24-hour hackathon. Two prize tracks are in play, and the project should be built to compete for either:

- **Track A — best project in the age group.** A conventional rubric: execution, polish, completeness, technical depth, real-world relevance, and a convincing demo. Visual quality and reliability carry heavy weight here.
- **Track B — best use of the `.tech` domain** (sponsor-provided). Judged on domain creativity specifically, not on overall project quality.

**Strategic relationship between the tracks.** They are not mutually exclusive, and the project must not be split into two half-built attempts. The correct strategy is to find domain ideas where **the creativity is also the best product decision** — where doing something surprising with the address makes the software genuinely better. Such ideas serve Track B by their strangeness and Track A by producing a stronger product. Ideas that are merely gimmicky (clever address tricks that leave the product unchanged) serve neither track well: Track A judges quality, Track B judges creativity, and a stunt with no product improvement has neither.

**Critical prerequisite for Track B:** a creative domain concept that is not deployed and reachable at that domain cannot win. Working deployment is the floor for *both* tracks, not just Track A.

**Team context:** 4 people, all Python-comfortable. One developer (the author of this codebase) works solo for the first ~9 hours, then the full team for the final ~3. Everyone is a beginner-to-intermediate Python developer. This constraint has driven nearly every scope decision below.

### 1.1 Track B: the domain must be load-bearing

The `.tech` prize goes to the **most creative at the hack.** This is not a quality rubric. It rewards the project that uses the domain in a way nobody else thought to, not the one that is best-engineered or best-designed.

**The test:** *would this idea still exist if it had to live at `myapp.com`?* If yes, the domain is decoration and the entry is weak. If the project genuinely could not work without a `.tech` address, it is competing for the right prize.

**Creativity is not gimmickry.** A novelty trick with no substance wins nothing. The strongest entries make the surprising use of the domain *also* the best product decision — where the weird idea makes the software better, not merely more surprising. This is the specific overlap that lets one build serve both tracks at once.

---

## 2. Design pillars

These are the load-bearing ideas. Any expansion should be judged against whether it strengthens one of them.

**2.1 Server-authoritative game rules. (preserved)** All rules that grant rewards live on the server. The game client is a renderer. This was a deliberate architectural choice so that the client is untrustworthy by construction, and so the game engine could be swapped without touching game logic.

**2.2 Derived, not stored, progression. (preserved, and extended in v2)** There is no `xp` column on the user record; total XP is computed by summing XP values from "room cleared" rows each time it is needed. This is the most technically interesting property of the codebase: cheating is not prevented by validation logic, it is *structurally impossible*, because there is no mutable field to edit. The public leaderboard and the personal history log are literally derived from the same rows, so they cannot diverge or be falsified independently.

**In v2 this pillar must be extended, not relaxed.** With XP dropped, the same rule applies to potions: potion *earning* is derived from completion rows in the current weekly window, and potion *use* gets its own append-only table, so `available = earned − used` remains a sum over rows rather than a counter. **The v2 design must not introduce a mutable `potions` or `progress` column** — doing so would trade away the codebase's best property for convenience.

**2.3 Append-only history. (preserved)** Completion records are never edited or deleted. Deleting a task archives it (`active = False`) rather than removing it, specifically so the friends-visible log remains intact. The history is the product's accountability feature and its source of game state simultaneously. It must also survive the weekly reset intact.

**2.4 Loss is never punished. — RETIRED in v2.** This pillar said losing a battle costs nothing: no XP loss, no progress loss, no streak break, retry or flee freely. The rationale was that this is a wellbeing-adjacent application, and punitive failure states in that category cause churn.

**The owner has dropped this pillar** (§0.2): losing should have a setback, such as returning to the last checkpoint. The exact penalty is **UNDECIDED** (§0.7 Q2). **The churn rationale above still constrains the design** — keep any setback mild, a checkpoint rather than stat or progress destruction.

**2.5 Timezone correctness. (preserved, extended)** Day and month boundaries are computed in the player's local timezone (configurable via `APP_TZ`, default `America/Vancouver`), never UTC. UTC midnight is 5pm in Vancouver; using it would reset daily quests at the wrong time. Timestamps are *stored* as naive UTC and *converted* for period logic. **v2 adds a third boundary: the week**, for the weekly dungeon reset. Same rule applies, and the week start day is still UNDECIDED.

---

## 3. What is implemented and verified (v1 — the current state of the code)

**This section describes the code as it exists today, which is v1.** Several of these rules are being removed or repurposed per §0.2: the unlock rule (§3.3), the XP and level formulas (§3.3), the health bonus term, and the XP columns on `/api/player`, `/api/rooms`, and `/api/leaderboard`. Read this section as "what exists," not "what should exist."

### 3.1 Technology stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.12+, FastAPI, Uvicorn | Async-capable, auto-generates API docs |
| ORM | SQLModel (SQLAlchemy + Pydantic) | Declarative tables; note version quirk in §6 |
| Database | SQLite locally, Postgres in production | One env var (`DATABASE_URL`) switches; no migrations, tables created at startup |
| Auth | Signed session cookie (Starlette `SessionMiddleware`) + stdlib PBKDF2-HMAC password hashing | No third-party auth or bcrypt dependency |
| HTML pages | Jinja2 templates | Thin shells; all data fetched from the JSON API client-side |
| Game client | Phaser 3 via CDN, vanilla JavaScript | No build step, no npm, no bundler |
| Styling | Hand-written CSS | Pixel-art aesthetic: VT323 + Press Start 2P fonts |
| Deployment | Render (render.yaml blueprint) + Postgres | Config written, not yet executed |

### 3.2 Data model (six tables)

- **User** — username (unique), password hash, created timestamp
- **Task** — title, kind (`daily` | `monthly` | `goal`), owning user, `active` flag, created timestamp
- **Completion** — append-only record linking a task to a moment it was completed. Fields: server timestamp, optional note, `flagged_by` (nullable FK to flagging user).
- **RoomClear** — a room beaten in-game. Fields: XP awarded, timestamp, and a **unique** foreign key to the `Completion` that justified it.
- **Item** — loot found: name, attack bonus, defense bonus
- **Friendship** — two user IDs as a composite primary key; rows are stored in both directions

The `unique=True` constraint on `RoomClear.completion_id` means the *database itself* refuses a second clear for one completion, independent of application logic — a second line of defence behind the API check.

### 3.3 Implemented game rules (all server-side, no I/O, unit-testable)

**Unlock rule.** A room is unlocked if its task has a completion within the current period: since local midnight (daily), since the 1st (monthly), or ever (goal). A single function, `completion_in_period`, is the sole authority — used identically by the room-listing endpoint and the clear endpoint, so the displayed state and the enforced state cannot disagree.

**Progression.**
- XP: daily 10, monthly 50, goal 200
- Level: `floor(sqrt(xp / 25)) + 1`; XP required for a level: `25 × (level-1)²`. Exact inverses, so the HUD can display "60 XP, next at 100" with two function calls.
- Player attack: `10 + 3 × level + sum(item attack bonuses)`
- Player defense: `sum(item defense bonuses)` (currently uncapped — see §5)

**Health as accountability.** `100 − 10 × (dailies missed in the last 7 days) + 5 × (any completions in the last 7 days)`, clamped to 0–100. Today is never counted as missed. Days before a task's creation date are never counted against the player. Deliberately, skipping costs more than completing rewards.

**Enemy generation.** Tier by task kind: daily → mob (30 HP, 5 ATK), monthly → mini-boss (70 HP, 8 ATK), goal → boss (120 HP, 12 ATK). Monster identity is seeded by task ID, so a given task always holds the same creature — a deliberate determinism choice, since the global random generator would reshuffle on every page load and read as a bug.

**Loot.** 60% drop chance from a six-item table with flat attack/defense bonuses.

### 3.4 Implemented API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/api/player` | Level, XP, HP, attack, defense, inventory |
| GET | `/api/rooms` | Every active task as a room: unlocked, cleared, enemy, XP value |
| GET/POST | `/api/tasks` | List / create tasks |
| DELETE | `/api/tasks/{id}` | Archive (soft delete, preserves history) |
| POST | `/api/tasks/{id}/complete` | Records a completion with a **server** timestamp. Rejects with 409 if already completed this period |
| POST | `/api/rooms/{id}/clear` | Grants XP + loot. Rejects 403 if the task is not completed this period; 409 if already cleared |
| GET | `/api/log?username=` | Completion history. Own log always; friends' logs only if friended |
| POST | `/api/completions/{id}/flag` | Friend flags an entry as suspicious |
| POST | `/api/friends` | Add by username, creates both directed rows |
| GET | `/api/leaderboard` | Self + friends, weekly XP, 7-day window |

Ownership violations deliberately return **404 rather than 403**, so the API does not confirm that another user's task ID exists.

### 3.5 Implemented pages

- **Login / Register** — single form, two submit actions
- **Quest Board** (`/tasks`) — add tasks by kind, press "I did it" to complete (prompts for an optional note), shows door-open/cleared state, archive button
- **Party** (`/friends`) — invite by username, weekly leaderboard with per-user log links
- **Adventure Log** (`/log`) — timestamped completions, own or a friend's; friends can flag entries
- **Dungeon** (`/play`) — HUD (level, HP bar, XP bar, attack, defense, inventory) above the game canvas

All page data comes from the JSON API via two shared helpers: `api()` (fetch wrapper that throws the server's `detail` message on failure) and `el()` (DOM builder that uses `textContent`, never `innerHTML`, so user-authored text cannot inject markup).

### 3.6 Implemented game client

Three scenes:
- **Boot** — fetches rooms and player state, waits for the pixel font to load before starting
- **Dungeon** — a straight horizontal chain of rooms separated by short walkways. Arcade-physics movement uses WASD/arrow keys and a following camera. Each uncleared enemy room has a barred exit; winning removes the gate and opens the next room. Cleared rooms show a chest, and walking into the current room's monster starts battle.
- **Battle** — turn-based, clickable or keyboard (1/2/3/Esc). Actions: Attack (12% crit, 0.8–1.2× damage variance), Power Strike (2.2× damage, 3-turn cooldown), Defend (reduces incoming damage to 30%, heals up to 6), Flee. HP bars, floating damage numbers, hit flash and shake tweens, particle burst on victory, level-up and loot announcements. Death offers a free retry.

**Art is currently placeholder**: simple shapes drawn programmatically into canvas textures at boot (`makeTextures`), so the game runs with zero asset downloads. This is the most visually obvious weakness (see §5).

### 3.7 Verification performed

**API-level (via HTTP against a live server):** registration and login (including wrong-password rejection); locked room cannot be cleared (403); task cannot be completed twice in a period (409); room cannot be cleared twice (409); one user cannot clear another's room (404); logs are inaccessible before friending (403) and accessible after; flagging works; leaderboard computes correctly; all HTML pages and static assets return 200.

**Timezone logic (unit-level):** a completion at 11pm Vancouver on Oct 3 correctly does not count toward Oct 4, and does count for that same evening. Monthly boundaries resolve correctly. HP penalty arithmetic confirmed.

**Browser-level (Playwright driving Microsoft Edge):** logged in via the real form, walked the hero into an unlocked room, confirmed the battle scene triggered, fought to a victory, confirmed XP/level-up/loot were granted and the HUD updated. Screenshots of all four pages captured and reviewed.

---

## 4. Explicitly not implemented

These were consciously deferred, not overlooked.

- **No photo or location proof of completion.** The design discussion concluded that software cannot verify that someone went to the gym, so the app should present an *append-only, server-timestamped log visible to friends* rather than claim enforcement. Optional evidence capture is a proposed extension.
- **No streaks, no rest days, no decay.** The dungeon shows current state only; it has no memory of how long the player has been away.
- **No enemy scaling.** Difficulty is fixed per tier and does not respond to player level (see §5.1).
- **No native mobile.** Not a PWA yet; the layout is not verified on a phone.
- **No real-time features.** No WebSockets; presence is not shown.
- **No notifications of any kind.**
- **No co-op or shared content.** All social features are read-only views of other people's data.
- **No deployment.** `render.yaml` exists but has never been run; the `.tech` domain has not been claimed; nothing is committed to git.
- **No automated test suite.** Verification was done with throwaway scripts, not a maintained test suite. `game.py` is deliberately I/O-free and unit-testable, which was designed to make this easy to add later.

---

## 5. Known weaknesses and bugs (v1)

Ordered by severity. These are the highest-value targets.

**Two of these are resolved by the v2 revision rather than by fixing them:** §5.1 and §5.2 are obsolete as written, because there are no levels or XP any more. They are replaced by a different balance problem — tune enemies against "player with full potions" versus "player with none" (§0.2). §5.3, §5.4, and §5.8 remain open. §5.6 is partly addressed by the weekly reset and the prepare-then-fight loop.

**5.1 Enemy difficulty never scales.** Enemy HP and ATK are fixed per tier, while player attack grows linearly with level and loot. By roughly level 5–6 the player one-shots bosses, and defense is uncapped, so accumulated defense eventually trivializes all content permanently. The game has approximately one week of content. Suggested fix: multiply enemy stats by `1 + 0.35 × (player_level − 1)`, and scale within a tier by how many times the task has been completed. Separately, apply diminishing returns to defense beyond a threshold.

**5.2 The reward curve devalues the target habit.** A daily task pays 10 XP; a one-time goal pays 200 XP. A single goal completion therefore out-earns twenty days of daily tasks, and the quadratic level curve amplifies this. The daily streak is the intended retention mechanism, and the current math actively argues against it. Suggested fix: a consecutive-day streak multiplier (up to ×2), reduced repeat XP for already-completed goals, and monthly XP that beats the daily drip.

**5.3 Placeholder art.** Code-drawn rectangles are the weakest thing on screen. This is an art problem, not an engine problem — the visual ceiling is set by the assets, not by Phaser. Free, permissively-licensed pixel art packs would transform the presentation in a small fraction of the time any feature work would take. This is the single highest value-per-hour improvement available.

**5.4 Accessibility gap.** Task type is currently communicated primarily by colour (green/orange/purple borders and room labels). For a colour-blind user, several rooms are indistinguishable. Needs a shape or glyph per kind, plus contrast verification and reduced-motion support for the tweens.

**5.5 The dungeon is a rendering, not a world.** Rooms are laid out in a fixed grid, one per task. Adding or clearing tasks feels the same each time; there is no sense of a place being returned to, and no progression beyond a number increasing.

**5.6 No day-7 retention mechanism.** The hardest problem in productivity software, entirely unaddressed. No streaks, no decay, no narrative, no reason to open the app on any particular day.

**5.7 Generic leaderboard.** Sorted weekly XP — the standard approach for the category. Creates comparison but not connection, and actively demotivates players who are behind (i.e. the players who most need the product).

**5.8 Weak onboarding.** A new account has zero tasks, so a first-time viewer sees an empty dungeon and may reasonably conclude this is a to-do list with a skin.

---

## 6. Technical notes and gotchas

- **SQLModel/Pydantic version quirk:** the installed version rejects naive `datetime` fields. Timestamp columns must be annotated `NaiveDatetime`, with values produced by a helper that returns `datetime.now(timezone.utc).replace(tzinfo=None)`.
- **`SECRET_KEY` must be set in production.** The app falls back to a random key, which invalidates all sessions on every restart — every deploy logs all users out. `render.yaml` generates a persistent one.
- **No migrations.** Schema is created from the model definitions at startup. Any schema change requires deleting the local database.
- **Windows encoding.** The system Python defaults to cp1252; scripted file edits must specify `encoding="utf-8"` (the templates contain emoji). One scripted edit truncated a template file before this was noticed.
- **No build step for the game.** Phaser loads from a CDN and `main.js` is served as a static file, so changes are visible on refresh and there is no toolchain to break.
- **Same-origin architecture.** The game, the HTML pages, and the API are one FastAPI application on one domain. This avoids all cross-origin request configuration, and means deployment is a single unit.

---

## 7. Directions for expansion (v1 roadmap — largely superseded by §0.8)

Ordered roughly by expected value per hour of the remaining hackathon time.

**Read with care.** Much of this roadmap assumed XP, levels, and locked doors, all of which v2 removes. §7.1's enemy-scaling and XP-rebalance items are obsolete (§5.1, §5.2). §7.2's streak and decay mechanics are largely displaced by the weekly reset and potion economy. §7.4's card-based loot idea is the seed of what became the v2 potion system, and is the most valuable thing here. **The suggested order of work is §0.8, not this section.** Items below are retained because parts remain useful — art (§7.1), accessibility, co-op raids, world structure, flavour text, onboarding, and the PWA move are all still live.

### 7.1 Fix the fundamentals
Enemy scaling by player level (§5.1), defence diminishing returns, a streak multiplier and rebalanced XP (§5.2), and real art assets (§5.3). These four convert a working prototype into a presentable product. Art is the cheapest and moves the score most.

### 7.2 Retention mechanics (the biggest conceptual gap)
- **Streak multiplier** on consecutive daily completion, the most proven retention mechanic in the product category.
- **Streak shrine** in the entrance hall whose braziers light per consecutive day — makes the streak visible in the world rather than as a number. Break it and the shrine goes dark.
- **Dungeon decay:** rooms visibly rot when the player is inactive — dust overlays, cracks, dimmer torches. Completing anything restores one room for free. Honest rather than nagging, visually cheap, and creates a reason to return specifically today.
- **Rest Days** (the most distinctive idea in this project): a Rest Room enterable *only* if nothing was completed that day, which fully restores health and grants a small bonus. Taking a day off becomes a strategic move, directly inverting the punitive streak model that every accountability app uses. Pairs naturally with streak freezes.

### 7.3 Reframe competition
Primary comparison becomes **the player against their own past self** ("last month 4 rooms, this month 11", personal bests, a ghost replay), with the friend leaderboard retained but opt-in and secondary. Better design *and* better ethics. Consider leagues/brackets so beginners are not exposed to power users.

### 7.4 Combat depth
- **Telegraphed attacks:** enemies visibly wind up ~1.2s before a heavy strike; defending during the wind-up negates and counters it. Roughly 30 lines, and it converts the fight from a race into a mind-vs-execution game. The highest-value combat addition.
- **Boss phases** at 50% health (enrage: faster, stronger).
- **Resistances** requiring deck-building.
- **Card-based loot** instead of flat stat bumps: items that change *how* combat works (e.g. "Defend heals 12 instead of 6", "Power Strike cooldown 4 instead of 3"). Makes the reward screen meaningful and gives each battle a decision.
- **Enemy variety within tiers:** a fast weak type, a slow heavy type, a healing type.

### 7.5 Social depth
- **Co-op raids:** a party-wide boss with a shared health pool that every member's quest completions damage. Turns friendship from purely competitive to cooperative, creates a reason to want friends to succeed, reuses existing data, and is a strong live demo moment. Needs two new tables.
- **Reverse accountability:** show friends' *missed* days, not just successes, and offer one-tap "nudge" for a friend stuck on the same task for days. Shifts the social layer from surveillance to support.
- **Cheer reactions** on completions — trivial to build, makes the log feel alive.
- **Presence indicators** — e.g. colored name tags for online party members in the entrance hall.
- Party chat and guilds, noted as post-hackathon scope.

### 7.6 World structure
- **Geometry generated from task structure:** dailies form a corridor (the most frequent action is the most available movement), monthlies form wings, goals form a boss arena that visibly extends as goals are added. Adding a task then changes the world, not just the room count.
- **Task dependencies** (`depends_on_id`) creating a shallow progression graph, so a boss requires its monthly prerequisites. Keep chains to two or three levels or the dungeon becomes a flowchart.

### 7.7 AI-generated flavour
One LLM call per task at creation time (not per request), cached on the task row, generating a bespoke monster name and one-line taunt — e.g. "Pay rent" → *Rentosaurus*, "Its jaw drops on the 1st. You know this." Pennies in cost, high delight, and the kind of detail that invites a judge to pick up the laptop. Requires a static fallback path so the demo never fails on a network error, and pre-generated flavour for seeded demo accounts.

### 7.8 Onboarding and demo
Pre-seed two accounts with three weeks of plausible history so the dungeon appears lived-in. Seed three example quests on registration so a first-time viewer never sees an empty dungeon. Engineer the "aha moment" into the first 60 seconds: press "I did it" → door visibly opens → walk in and fight.

### 7.9 Narrative layer
The completion log is currently a table. It could instead be the product's story: a weekly recap ("you cleared 9 rooms and lost 4 health to the Sedentary Wyrm"), plus forecasting from existing data ("you complete 68% of dailies; at that rate, 9 rooms this week"), and a year-in-review.

### 7.10 Platform
Convert to a PWA (manifest, service worker, icons) so judges can install it from the same codebase — the highest-leverage mobile move available. Verify the current layout works on a phone before investing further; judges will open the link on their phones.

---

## 8. Pitch framing

**Current framing to avoid:** "anti-cheat" or "prevents cheating." Software cannot verify that a person completed a real-world task, so this claim invites immediate and deserved skepticism from any thoughtful judge.

**Recommended framing:** the value is *social accountability*, delivered through an append-only, server-timestamped log visible to friends who can flag entries. Combined with the structural property that progress is **derived rather than stored** — so the leaderboard and the log cannot diverge or be falsified independently.

**Strongest single line:** the dungeon is powered by the player's real life; progress cannot be bought with in-app actions.

**Strongest technical demonstration:** that progress exists only as a sum over derived rows rather than as an editable field, and that the server rejects rewards it cannot justify from real completions.

**Caveat for v2.** The original demonstration was *clearing a room for an incomplete task is rejected with 403* — but v2 removes the gate, so that specific demo no longer exists (§0.2). The demonstration must be rebuilt around the potion economy: show that potion inventory is computed from the append-only completion log, that a client sending an inflated potion count is rejected, and that the leaderboard is a sum over the same rows as the personal log. The underlying architectural claim is unchanged and still the strongest thing in the project; only the illustration needs replacing.

**Likely judge questions, with prepared answers:**
- *"Isn't this just a to-do app with a skin?"* — The game is the retention mechanism, and retention is the product. Most to-do apps lose 90% of users by day 30. The reason this one might not is that you open it to walk into a room, not to stare at a checkbox.
- *"What if someone just marks everything done?"* — We don't prevent it, and we don't claim to. We make it visible and socially costly: a permanent, server-timestamped log your friends can read and flag.
- *"What makes this hard?"* — All game rules are server-authoritative and progression is derived from an append-only log, so the client cannot be trusted or edited. The game engine could be swapped without touching game logic. *(Note: the derived-not-stored claim survives v2 intact, but "progress" now means potions earned and leaderboard depth rather than XP — see the caveat in §8.)*
- *"Why Phaser and not Godot/Unity?"* — No build step, trivial API integration, instant load, and the constraints that matter to the design live on the server.

---

## 8.1 Creative use of the .tech domain (the actual prize criterion)

This section exists because the prize is for domain creativity, not for overall quality. Each idea below is scored on whether the project would be materially worse without a `.tech` address.

**The subdomain-as-level idea.** Serve the dungeon from subdomains of the registered domain, where each subdomain is a distinct layer of the dungeon: `floor1.your.tech`, `floor2.your.tech`, `boss.your.tech`. Deep-link a friend directly to the boss arena they need to help with. Each floor can be a separate container or route with its own state and its own shareable URL. *Why it needs a domain:* wildcard subdomains and per-floor addressing are the entire mechanic; the shareable "come help me on floor 3" link only works if floors are independently addressable. Cheap to implement with wildcard DNS pointed at one backend, where the subdomain selects the level.

**The domain as the party identity.** Give each user a claimed subdomain rather than a username — `kai.yourdomain.tech` is your character sheet and your shareable profile. Your party list is literally a list of subdomains. *Why it needs a domain:* a namespace you control, that you can hand out to users, is a genuinely scarce resource at a hackathon, and the sponsor domain is the only source of one. This also makes the accountability log feel like a public artifact with a permanent address.

**A shared persistent world.** One dungeon for the whole hackathon, where every registered user's rooms are inserted into the same map and anyone can walk through everyone else's dungeons. A leaderboard board becomes a literal dungeon floor that fills up over 24 hours. *Why it needs a domain:* the value is the memorable shared address at which the collective world lives, and the address is what people share. This is also the strongest possible demo artefact — a map that visibly grows all weekend.

**TLD as the game's theme.** `.tech` is a technology TLD. Lean into it rather than treating it as neutral: the dungeon is a decaying machine, rooms are subsystems, the boss is the central daemon, XP is "committed," and the log is a commit history. The domain becomes the fiction rather than the venue. *Why it needs a domain:* the naming and framing only land if the address itself is `.tech`.

**Honest assessment.** The first three are the strongest because the domain is genuinely load-bearing. The fourth is cheap and effective as a coat of paint. Subdomain-per-floor has the best ratio of impressiveness to implementation cost — wildcard DNS plus a subdomain-sniffing middleware is perhaps thirty minutes of work, and it is the kind of thing a judge has not seen before.

**Connection to v2.** The subdomain-per-floor idea fits the new model naturally: since progress becomes "which floor you are on," each floor gets its own shareable address. This makes it the strongest candidate under the revised design, and it is the one that also improves the product rather than decorating it.

**The domain is registered: `mylost.tech` (as of 2026-10-04).** The idea is still undecided. Concrete forms the four candidates take with this domain: `floor1.mylost.tech` / `boss.mylost.tech` for subdomain-as-level, `kai.mylost.tech` for party identity, `mylost.tech` for the shared world, and `mylost.tech` again for the TLD-as-theme framing. The first two need a **wildcard** DNS record (`*.mylost.tech` CNAME to the same Render target) rather than two host records; `mylost.tech` and `www.mylost.tech` are already declared in `render.yaml`.

**Note on the fourth idea:** its framing ("XP is *committed*") depends on XP, which v2 has dropped. If it is chosen, its flavour text needs rewriting — the equivalent line is that potions are *distilled*, and the log is a commit history.

---

## 9. Constraints for anyone continuing this work

- **Two prize tracks are in play (§1).** Serve both with one build. When time forces a choice, prefer the domain idea that *also* improves the product — it is the only option that scores on both axes. Never let Track B work degrade Track A quality, since a working, polished project is what Track A judges.
- **Deployment is the critical path, not a wrap-up task.** `render.yaml` exists but has never been run. `mylost.tech` is registered and now declared in the blueprint, but no DNS record points at it yet. Subdomain routing for §8.1 **cannot be tested without a live address**, so get a bare "hello" version on the domain early, before adding features, and deploy a minimal build in parallel with feature work (§0.8 step 11).
- **Demo-breaking risks, all of which have bitten before:** a live database that sleeps, a missing or rotated `SECRET_KEY`, and data that does not survive a redeploy. **Verify data survives a redeploy before the presentation window** — do not assume it.
- **Time:** approximately 3 hours of team time remained in the original hackathon window per v1. **Confirm the current figure with the owner — this figure is almost certainly stale.**
- **Skill mix:** the team is Python-comfortable and beginner-to-intermediate. Frontend and game code are less well covered, so favour backend changes and mechanical tasks that can be delegated (art sourcing, styling, seeding scripts, deployment).
- **Single deployable:** game, pages, and API must remain one origin. Avoid introducing anything that requires cross-origin configuration.
- **The rule engine must stay engine-agnostic.** All reward and unlock logic belongs in the backend so the client remains swappable.
- **Ask before building on undecided ground.** §0.7 lists eleven open questions. Batch them for the owner rather than guessing — several (stat source, leaderboard, health) change the shape of the code, and guessing wrong wastes a teammate's balancing work.
