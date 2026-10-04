# Task Dungeon — Pitch & Product Ideas

Brainstorm document. Nothing here is implemented; it's a menu for the remaining hackathon hours and for after. Ordered roughly by expected value, with the honest problems up front.

---

## 1. Honest assessment

### What's genuinely strong

- **The one-sentence pitch.** "Your to-do list is a dungeon; the doors only open when you do the thing." That survives being heard once, across a room, by someone who's tired. Most hackathon projects don't have that.
- **The server-side XP derivation.** Not having an `xp` column on `User` means the leaderboard and the log are literally the same data. Cheating isn't prevented by validation; it's structurally impossible. This is the most technically defensible part of the project and it's worth *saying out loud* during the demo.
- **Fighting is optional and free.** Losing costs nothing. For an app about self-improvement, punitive failure states are a genuine design risk, and this avoids it.

### What's weak, ranked by how much it hurts

**1. Difficulty never scales.** `enemy_for()` returns fixed HP and ATK per task kind. Player attack is `10 + 3 × level + sum(item.atk)`. By level 5 you're one-shotting the boss, and stacking defense is unbounded (`max(1, dmg - defense)` means enough defense trivializes everything forever). There is no content past roughly level 6. *This is the biggest gap in what you've built.*

**2. The reward structure devalues the habit you're selling.** A daily quest pays 10 XP; a one-time goal pays 200 XP. So a single goal completion — one afternoon's work — out-earns twenty days of daily quests. The leveling curve is quadratic, which makes it worse. The daily habit is your retention engine and the math actively discourages it.

**3. "No cheating" is a promise you can't keep, and it's the wrong frame.** Software cannot verify someone went to the gym. Leading with anti-cheat invites the obvious question from any judge who thinks for five seconds. The log is genuinely valuable, but it's valuable as *social accountability*, not as enforcement.

**4. The dungeon is a rendering of the task list, not a world.** Rooms are generated 1:1 from tasks in a fixed grid. Clearing everything and adding one task feels the same. There's no sense of a place you're returning to, and no progression that isn't a number going up.

**5. Nothing brings people back on day 7.** This is the hardest problem in all of productivity software and the current design has no answer. No streaks, no decay, no narrative, no reason to open the app tomorrow specifically.

**6. The leaderboard is generic.** Weekly XP, sorted. Every habit app has this. It creates comparison but not connection.

---

## 2. The pitch

### Reframe the headline

| Current | Problem | Suggested |
|---|---|---|
| "Ensure no cheating" | Unkeepable promise; invites skepticism | "Your party can see your log" |
| "Friendly competition" | Understates the mechanic | "Accountability you actually feel" |
| "RPG mechanics" | Generic | "Your habits are load-bearing" |

The strongest single framing: **the dungeon is powered by your real life.** Not gamified. *Literally powered.* The game cannot progress without you acting, which is the opposite of every achievement system where progress is a button press.

### Naming

"Task Dungeon" is clear and fine. If you want more character: *Dungeonbound*, *Questlog*, *The Dungeon Ledger*, *Room for Effort* (bad). Honestly the current name is better than most alternatives — clear beats clever for a 2-minute pitch. Spend the time elsewhere.

### The demo is the product

In a hackathon, the demo *is* the project. Budget real time for it.

**The 2-minute script:**
1. (15s) Open the app already logged in. Show a dungeon with a mix of open and locked doors.
2. (30s) Point at a locked door. "That's 'Pay rent.' It opens when I actually pay rent. Not before."
3. (45s) **Live:** press "I did it" on a task. The door opens *on screen*. This is the moment.
4. (45s) Fight. Win. XP and loot pop. HUD updates.
5. (30s) Switch to a friend's account. Their log shows a completion from 3 hours ago. Flag it as suspicious. **The social proof moment.**
6. (15s) Land the thesis.

**Do this before anything else:** pre-seed two accounts with weeks of plausible history so the dungeon looks *lived in*. A dungeon with 3 rooms and an empty leaderboard reads as a prototype. A dungeon with 30 rooms, level 12, real loot, and two rivals on the board reads as a world.

**Have a fallback video.** WiFi fails in hackathon venues. Record the demo at 1080p, have it on your laptop and on a USB stick.

---

## 3. Game design

### Scale enemy difficulty to player level (highest-value fix)

Make `enemy_for` a function of both the task and the player's level:

```python
def enemy_for(task, player_level):
    spec = ENEMY_BY_KIND[task.kind]
    scale = 1 + 0.35 * (player_level - 1)
    return {..., "hp": round(spec["hp"] * scale), "atk": round(spec["atk"] * scale)}
```

Then scale *within* a tier: a daily you've done 30 times should hold a tougher monster than a daily you've done once. This costs about fifteen lines and converts the game from "done in a week" to "endless."

Also **cap defense** or make it diminishing-returns, or the game trivizes itself:

```python
effective_defense = defense if defense < 10 else 10 + (defense - 10) * 0.25
```

### Fix the reward curve

Make sustained effort beat one big task:

- **Streak multiplier.** Consecutive days of hitting your dailies, up to ×2. This directly rewards the habit you're selling, and streaks are the single most effective retention mechanic in this entire product category.
- **Diminishing goal XP.** A goal pays 200 XP once, then 40 XP for repeat milestones on the same goal.
- **Monthly XP should beat daily-per-day.** One monthly (50) vs ~30 dailies (300) — the monthly should feel like the bigger deal. Raise it, or add a monthly-only bonus like a rare loot drop.

### Streaks as a dungeon mechanic, not a number

Make the streak *visible in the world*:

- A **streak shrine** in the entrance hall. Its brightness and the number of braziers lit reflect your current streak. Break it and the shrine goes dark.
- At 7 days, a **bonus door** opens to a rare room with good loot.
- At 30 days, a **streak boss** spawns — a real fight, high rewards.

The shrine gives you a reason to open the app *specifically* today, which is the retention hook the current design lacks entirely.

### Decay — the strongest retention idea here

**The dungeon rots when you stop playing.** Missed dailies don't just cost HP; the rooms visibly decay. Dust overlays. Cracks in the walls. Flickering torchlight. The entrance hall gets darker each day you don't complete anything, and there's a **Restoration** action (free, costs nothing, just requires completing anything) that cleans one room.

This works because:
- It's honest — you're falling behind, and the game shows it instead of a notification.
- It's ambient rather than nagging.
- It creates a reason to return *specifically today*, which streaks alone don't.
- It's visually cheap to implement (a tint and a particle effect per room).

### Procedural layout from task structure

Right now rooms sit in a fixed grid. Instead, let the *shape* of your task list determine the map:

- Daily quests become a **corridor** you walk down. Fast, rhythmic, a daily march.
- Monthly quests become **wings** off the corridor.
- Goals become a **boss arena** at the far end, and the corridor leading to it visibly extends as you add goals.

Now adding a task *changes the world*, not just the room count. This is cheap (it's grid math you already do) and it makes the dungeon feel authored rather than generated.

### Deckbuilding instead of item shopping

Loot currently gives flat `+atk`/`+def`. Make loot **cards** that change how you fight:

- *Heavy Blade:* +8 ATK, but your Power Strike cooldown goes 3 → 4
- *Warding Cloak:* Defend heals 6 → 12
- *Vampiric Fang:* +30% lifesteal on Power Strike
- *Second Wind:* once per battle, survive a lethal hit at 1 HP

Three or four cards in your deck changes decisions per battle. It also gives the reward screen something to be *about* — right now "you got Chainmail, +0 ATK +4 DEF" is a non-event.

### Boss mechanics that aren't "more HP"

- **Phases.** Bosses change behavior at 50% HP (enrage: faster, weaker hits). One line of state tracking.
- **Telegraphs.** A boss winds up for 1.2s before a heavy hit. Player defends correctly → reward. This is the single most satisfying thing you can add to a turn-based fight and it's maybe thirty lines.
- **Resistances.** Bosses are weak to a card type. Forces deck-building.

### Co-op raids — the best social feature

**A party-wide boss with a shared HP bar.** Every quest anyone in the party completes that day deals damage. The boss has a health pool; the party collectively grinds it down.

Why this is the strongest social idea in the document:
- It makes the leaderboard *cooperative* as well as competitive. Right now friends are rivals only.
- It creates a reason to genuinely want your friends to succeed.
- It's a natural demo moment: everyone's phone open, shared HP dropping.
- It reuses everything you already have. The data model needs one new table.

```python
class Raid(SQLModel, table=True):
    id, name, max_hp, current_hp, ends_at
class RaidContribution(SQLModel, table=True):
    raid_id, user_id, damage, xp   # damage derived from that day's XP
```

### Roguelike permadeath — pitch it, maybe don't ship it

Abandoning your run for a week could cost you progress. It's a great *pitch* line ("the dungeon doesn't care about your streak") and a terrible *product* decision for a wellbeing app. Consider a soft version: an abandoned run doesn't kill your account, it just stops your bonus streak from compounding.

---

## 4. Accountability and social

### Drop "anti-cheat," add verification

Reframe from enforcement to evidence. Then add real optional proof:

- **Optional photo proof** on completion. Not required, never enforced, but visible in your party's log. Social pressure does the work.
- **Location check** as an opt-in "hard mode" for gym/errand quests. Use a coarse check (did you leave the house) not GPS tracking. Being careful here matters — location access is a trust cost.
- **Stakes.** Optional, opt-in: put something on the line. "$5 to the party pot if you miss a week." Real stakes are the only thing that makes a log matter.

### Reverse the accountability

Currently friends see your *successes* and can flag them. Make the log symmetric and useful in both directions:

- Show **missed days** too, not just completions. "Alice missed 3 dailies this week."
- **Automatic party nudges.** If a friend is stuck on the same daily for five days, offer to nudge them. Turns the social layer from surveillance into support.
- **Cheer reactions.** 👏 on a friend's completion. Trivial to build, and it makes the log feel alive instead of clinical.

### Presence

Show who's online in the dungeon right now. Even just colored name tags in the entrance hall. Cheap with polling; real-time needs WebSockets.

### Party chat per room

A single shared text channel per room, or per party. This is the feature that turns a leaderboard app into a social app, and it's a weekend of work you probably don't have. Note it as a post-hackathon item.

### Guilds

For friend groups > 5. A guild leaderboard, shared raids, guild chat. Post-hackathon.

---

## 5. Systems worth reworking

### Data model additions

| Table | Why |
|---|---|
| `Streak` (or derived) | Core retention metric. Derive it from completions rather than storing — same anti-cheat property as XP. |
| `Task.depends_on_id` | Let a goal require its monthly prerequisites. Completing the chain unlocks the boss room. Adds a real progression graph. |
| `Evidence` | Optional photo/location proof attached to a completion. |
| `Raid` + `RaidContribution` | Co-op bosses. |
| `Completion.period_key` | A denormalized `"2026-10-04"` / `"2026-10"` column so period logic is a simple indexed query instead of a date comparison in Python. |

### The log is your most underrated asset

Right now it's a table. Consider making it **the narrative**:

- "On Oct 3 you cleared *Go for a run* at 7:12am. Three days earlier you missed it. That was the streak."
- Weekly recap email or in-app: rooms cleared, streak status, biggest rival, what your party did.
- **Year-in-review** energy, 20 minutes early. Judges love these.

This costs one query and one template, and it converts a database table into a story.

### Mobile

**Don't build native.** A **PWA** (add a manifest, a service worker, an icon, `viewport-fit=cover`) gets you an installable app on iOS and Android from the same codebase. For a hackathon where judges will open it on their phones, this is the single highest-leverage mobile move.

Realistically: judges will open the link on their phone. **Test that it works on a phone before you build anything else mobile.** The HUD and quest board may need a responsive pass.

---

## 6. Technical

### Phaser vs Godot — the honest version

You have ~50 hours of Godot and some JS. Phaser is built and tested. The plan said we'd revisit at hour 5 based on how the Phaser result feels.

My honest read: **stay with Phaser.** Reasons: it's working, it needs no export step, the API connection is trivial, and the remaining hours are better spent on *balance and social features* than on a renderer swap. Godot's advantage is visual polish — and you're currently using code-drawn placeholder art, which means the ceiling on "looks good" is set by the art, not the engine. Fix the art first; it's the cheaper win.

If you do switch: all rules are in `game.py` and all state transitions are in `routes/api.py`, so a Godot client only needs to render `/api/rooms` and call `/api/rooms/{id}/clear`. The swap is genuinely cheap — that's why the rules were kept server-side.

### Art — the highest-leverage non-code work

This is what separates "cool prototype" from "wow." Right now the art is code-drawn rectangles and that's the weakest thing on screen.

- **Kenney.nl** — free, CC0, no attribution required. "Tiny Dungeon" and "1-Bit Pack" are exactly the right register.
- **itch.io** — 0x72's DungeonTileset II is the gold standard for top-down pixel dungeon. Free.
- Pick one pack and be consistent. Mixed art reads as amateur faster than simple art.

This is a genuinely good task to hand a teammate who isn't doing backend work.

### Deployment

- **Postgres on Render** is configured in `render.yaml`. Verify data survives a redeploy — that's the single most common hackathon deploy failure.
- **Set `SECRET_KEY`.** It's in `render.yaml` as a generated value. Without it every deploy logs everyone out, which will look broken during judging.
- **Seed script.** A `scripts/seed.py` that creates two believable accounts with weeks of history. Judges should never see an empty app.

### Other technical options if time allows

- **Rate limiting** on `/api/login` so the demo can't be griefed.
- **Optimistic UI** on the quest board so "I did it" feels instant.
- **Sound.** A door-opening sound is worth more than you'd think. Three small files.
- **WebSockets** for co-op raid presence. Only if the raid feature lands.

---

## 7. Hackathon tactics

### What to cut if you're behind

Cut in this order — least damaging first:

1. Loot item variety (keep the mechanic, shrink the table)
2. Battle polish (tweens, particles — it's playable without them)
3. Monthly/goal distinction (everything becomes a daily; lose the pitch nuance, keep the game)
4. The flagging feature (it's a nice story beat, not a system)

**Never cut:** the server-side XP derivation, the unlock gate, the log, or the demo seed data. Those are the project.

### What to build if you're ahead

1. Co-op raid (best social payoff)
2. Streak shrine + multiplier (best retention payoff)
3. Dungeon decay (best visual payoff, cheapest of the three)
4. Real art
5. Photo proof

### Team split for the last 3 hours

| Person | Job |
|---|---|
| Backend | Seed script, deploy, Postgres verification |
| Art | Real sprite pack, logo, favicon, loading screen |
| Frontend | Mobile responsiveness pass, the one ugly page |
| Pitch | Devpost, demo script, rehearse it twice |

Hand out the demo script as a document. Two people rehearsing beats four people improvising.

### Judging

Most hackathon rubrics weight: technical difficulty, execution/polish, and real-world relevance — roughly equally. This project's honest strengths and weaknesses against each:

- **Technical difficulty:** moderate-to-good. The server-authoritative game rules and the append-only log are legitimately interesting. Co-op raids would push this higher.
- **Execution/polish:** currently the weakest axis, and it's almost entirely an *art* problem. Fixable in two hours with a free asset pack.
- **Real-world relevance:** strong. Task management + accountability is a real problem with real suffering users, and you can name them personally.

**The axis you're weakest on is polish, and it's the cheapest to fix.** Prioritize art over features.

---

## 8. If you have to pick three

1. **Real art pack + a loading screen.** Cheapest path to "this looks like a product."
2. **Enemy scaling + streak multiplier.** Turns a toy into a game with a long tail.
3. **Pre-seeded accounts + rehearsed demo.** Multiplies the value of everything else.

Co-op raids are the fourth, and the best "wow" story if you have a fifth hour.

---

## 9. Post-hackathon

If it lives past Sunday:

- Native mobile (React Native or Flutter sharing the FastAPI backend)
- Guilds, party chat, real-time raids
- Integrations: Google Calendar, Todoist, Apple Reminders
- Habit science: did dungeon players actually complete more tasks? That's a real research question and a legitimately interesting paper.
- The `.tech` domain is a real product. A landing page, waitlist, and "your dungeon generated from your calendar" would be a genuine product concept.

## 10. The first five minutes (underexplored, high leverage)

The demo is judged in the first 30 seconds of looking at it, and users churn in the first session. Both are won or lost here.

**Never start empty.** A new user with zero tasks sees an empty dungeon and concludes "this is a to-do app with a skin." Seed three quests at registration — two dailies and one goal — with a note that they can be deleted. Better: make the *first* quest a real tutorial room. "Learn how this works" unlocks when you understand the loop.

**Engineer the aha moment.** The moment is: *I did a real thing, and a door opened.* Make sure it happens within 60 seconds. Concretely: on the quest board, the first time someone presses "I did it," respond with a little animation and an arrow pointing at the Dungeon tab. Then the first room they enter should be unlocked and waiting.

**Show the consequence, not just the action.** "I did it" → "🔓 Pay rent — Door open." Not just a checkmark.

**Pre-seed the demo accounts.** Restated because it's the single highest-value five minutes of prep: two accounts with three weeks of plausible history, so the dungeon has 30 rooms, the leaderboard has rivals, and the log has a story. An app with three rooms reads as a prototype no matter how good the code is.

---

## 11. The mechanic nobody expects: Rest Days

Every accountability app is quietly anti-rest. Streaks punish a day off, which means the day you most need to rest is the day the app tells you you've failed.

**Invert it.** A **Rest Room** in the entrance hall that you can only enter if you have completed *nothing* that day. Entering it fully restores HP and grants a small XP bonus. Taking a day off becomes a *move*.

This is the most distinctive idea in this document. It's genuinely good design, it costs maybe forty lines, and it makes an ethical argument judges notice: this app doesn't want you to use it every day. That's a real differentiator from every streak app, and it's the kind of thing that sounds great in a demo because the judges go "wait, *rest* is rewarded?"

Pair it with **streak freezes**: if you have a 20-day streak and you take a logged Rest Day, the streak survives.

---

## 12. Rival yourself, not your friends

The leaderboard pits you against people. For someone who's behind — the exact person who needs the app most — that's demotivating, and they'll leave.

**Show "you vs. your past self"** as the primary comparison:

- "Last month: 4 rooms. This month: 11."
- A **ghost run** of your previous self replaying the dungeon.
- Personal bests per quest.

Keep the friend leaderboard, but make it opt-in and secondary. The primary frame should be progress against your own history. This is both better design *and* better ethics, which is a rare alignment.

Also consider **leagues** (bronze/silver/gold brackets by XP) so a beginner isn't humiliated by a power user, and a **struggle mode** for anyone under a threshold.

---

## 13. Push back on the user

Real risk: someone adds fifteen daily quests, feels buried, and quits. The dungeon makes this worse, because fifteen rooms of red doors feels like failure.

**Cap dailies at 3-5 in the UI.** When someone tries to add a sixth, say so: "Dungeon crawlers carry 3-5 daily quests. Archive one?" Pushback is a feature — a to-do app that accepts unlimited tasks isn't helping anyone.

Related: **make the dungeon legible about why it's hard.** If a player has 12 locked rooms and 0 HP, the game should say so plainly rather than letting them wander. "You're not strong enough for the boss arena. Clear 3 dailies first." Clear failure is kinder than ambiguous failure.

---

## 14. LLM-generated flavor (uses setup you already have)

You already have OpenRouter wired up. Use it for something that isn't a gimmick.

**When a quest is created, make one API call to generate a monster name and a one-line taunt**, then cache it in the database:

| Quest | Monster |
|---|---|
| "Go for a run" | *The Procrastination Wyrm* — "It has been waiting. It knows about the couch." |
| "Pay rent" | *Rentosaurus* — "Its jaw drops on the 1st. You know this." |
| "Email professor" | *The Awkwardness* — "It shrinks when you write 'Dear'." |

Cache on the task row, generate once, never per-request. Cost is pennies. Delight is high, and it's the kind of detail that makes a judge pick up your laptop and try it.

**Extend it:**
- A dungeon name generated from your task distribution. "The Dungeon of Deferred Inbox."
- A boss's opening line, tailored to how long you've been avoiding the quest.
- Weekly recap written as flavor text: "You cleared 9 rooms and lost 4 HP to the Sedentary Wyrm."

Be honest in the demo that it's an LLM call — and have a **static fallback** for when the API is down, so the demo never breaks on a network error. Pre-generate flavor for your seeded accounts.

---

## 15. Combat depth

**Telegraphed attacks** are the highest-value combat addition. The boss winds up visibly for ~1.2s before a heavy strike; defending during the wind-up negates it and grants a counter. Roughly thirty lines, and it turns a fight into a mind-vs-execution game instead of a race where you mash Attack.

**Phases.** At 50% HP the boss enrages: faster turns, stronger hits, new sprite tint. One state variable.

**Resistances and counters.** Each enemy resists one damage type. Forces deck-building.

**Enemy variety within a tier.** Right now daily mobs share one template. Even three behaviors — a fast weak one, a slow heavy one, a one that heals — makes dailies varied for the cost of a `behavior` field.

---

## 16. Dungeon geometry from your task graph

Rooms sit in a fixed grid now. Instead, let the *shape* of your task list generate the map:

- **Dailies → a corridor.** Fast, rhythmic, a daily march. Your most frequent action is the most available movement.
- **Monthlies → wings** branching off the corridor.
- **Goals → a boss arena at the far end**, and the corridor visibly extends toward it as you add goals.
- **Completed-this-period rooms get a lit torch**; locked rooms are dark. Walking past your week is a visual summary.

Adding a task then *changes the world*, not just the room count. This is grid math you already do, and it makes the dungeon feel authored instead of dumped.

---

## 17. Task dependencies — a real progression graph

Add `Task.depends_on_id`. A goal can require its monthly prerequisites; completing the chain unlocks the boss room.

This gives the dungeon **structure and a sense of a campaign** — a boss you can't rush, a sequence that makes sense. It also creates natural XP pacing, because you can now tune XP per node in a chain rather than per task kind.

Beware turning it into a project-management tool. Keep chains shallow (two or three levels) or the dungeon becomes a flowchart.

---

## 18. Forecasting — predictive, not prescriptive

You already have the data to answer "am I actually going to do this?"

- "You complete 68% of your dailies. At that rate you'll clear 9 rooms this week."
- "You're on track to beat your best month."
- "You've missed this one four weeks running. Archive it?"

This is the difference between an app that nags you about the past and one that helps you plan. It's one query and a little statistics, and it feeds directly into the weekly narrative.

---

## 19. Time-of-day and friction

- **Morning/evening tags.** A quest completed before noon can pay a bonus. Real behavior nudge, trivially implemented, and it gives the day a rhythm.
- **Reset countdown.** "Dailies reset in 3h 20m." Creates a small, legitimate sense of urgency. Also a genuinely useful reminder.
- **Notification hygiene.** If you add notifications, make them opt-in and rare. Notification spam is how these apps get uninstalled.

---

## 20. Accessibility — there's a real bug here

Task type is currently communicated **primarily by color** (the green/orange/purple border on the quest list, the room label color in the dungeon). For a colorblind user that's several rooms reading as identical.

- Add a **shape or glyph** per kind: ▲ daily, ◆ monthly, ★ goal.
- Ensure sufficient contrast on the palette; the muted purple on dark purple is likely failing WCAG AA.
- Keyboard navigation for the game, since it's arrow keys already.
- Respect `prefers-reduced-motion` for the tweens and screen shake.

Worth fixing regardless of hackathon — it's cheap and it's the kind of detail that reads as competence.

---

## 21. Privacy and legal, if you build evidence features

If you add photo proof or location: store uploads outside the web root, or you will eventually serve someone's gym selfie to the wrong person. Be explicit in the UI about what friends can see. Make every evidence feature opt-in and clearly described. Do not build location tracking you don't need — location access is a trust cost disproportionate to its value here.

---

## 22. Failure modes to think about now

- **The demo breaks on venue WiFi.** Pre-generated flavor, local fallback assets, a recorded video.
- **The database dies mid-demo.** Render Postgres free tier sleeps after inactivity. Keep the app warm during judging, and know the wake-up time.
- **You get asked "what if someone just marks everything done?"** Answer: that's what the log and the party are for — we make it visible and socially costly, not impossible. Have this sentence ready.
- **You get asked "isn't this just a to-do app with a skin?"** Answer honestly: the game is the retention mechanism, and the retention mechanism is the product. Most to-do apps die at 10% 30-day retention. The reason ours might not is that you open it to walk into a room, not to stare at a checkbox.
- **A judge asks what makes this hard.** The answer is that all game rules are server-authoritative and XP is derived from an append-only log, so the client can't be trusted or edited. Then show them a room clear failing when the task isn't done.

---

## 23. On Godot, one more time, with fresh eyes

Stay with Phaser. The remaining hours buy more from art and balance than from a renderer swap, and the visual ceiling is currently set by placeholder rectangles, not by the engine. Fix the art first — it's a two-hour task with a free asset pack, and then reassess. The server-side architecture means a swap stays cheap if you want it later.

---
