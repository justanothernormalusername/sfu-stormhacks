# Task Dungeon: About the Project

## Inspiration

We wanted to make a productivity tool that felt less like staring at another checklist. A task app can record what we intend to do, but it rarely makes that effort feel tangible or gives us a reason to come back tomorrow. We started with a simple question: what if the game could only be powered by things we did away from the screen?

That became **Task Dungeon**: a turn-based RPG where real-life quests prepare us for the adventure. Finishing a task does not hand us a victory; it gives us supplies for a fight we still have to win. The idea keeps the game connected to real effort while leaving room for strategy, discovery, and a little bit of dungeon-crawling drama.

## What it does

Task Dungeon gives each player a shared, 12-room dungeon that changes every week. Everyone sees the same map, from the first enemies to the final boss, and can compare how far they got with their party.

Outside the dungeon, players create daily, monthly, and one-time goal quests. Completing a quest earns potions for the next battle: daily quests grant one, monthly quests two, and goals four. A lightweight task classifier can suggest whether a quest should earn a healing, damage, haste, or shield potion. The quantity is determined by the server, and keyword rules keep the feature working when the optional model is unavailable.

Potions are not an editable inventory counter. The app derives what is available from completions and recorded uses:

$$
	ext{available potions} = \text{potions earned} - \text{potions used}
$$

Players take those supplies into Phaser battles, where winning advances their weekly dungeon progress. Defeat costs the potions used in that fight and sends the player back to their last cleared room. A server-timestamped activity log gives friends a way to see and flag entries; it supports accountability without pretending software can verify what happened offline.

## How we built it

We built the application as one FastAPI service, with SQLModel and SQLite for local development and a Postgres-ready deployment configuration. Jinja templates provide the pages, while a Phaser 3 client renders the dungeon and battles. Keeping everything on one origin let the game call the API directly without a separate frontend build pipeline.

The backend owns the rules. Pure game functions generate the weekly map, define local-time periods, and calculate earned inventory. The map is deterministic for a given week, so every player gets the same rooms and enemy placements. Balance values live together in one configuration module, making it practical for teammates to tune combat without hunting through the client and server for duplicated numbers.

We also kept progression tied to records rather than trusting values sent by the browser. Completions and potion uses are recorded, and the server recomputes the inventory before allowing a potion to be spent. That gives us a compact rule to build around: the client can show the game, but it does not get to award itself supplies.

## Challenges we ran into

Our biggest challenge was changing the core loop. The first version treated each task as a room and completion as the key to its door. As we worked through the idea, that started to feel like a checklist with dungeon art. We redesigned tasks as preparation instead: defeating an enemy opens the next room, while real-life effort supplies the potions needed to survive. That made the two halves of the product work together.

The redesign also forced us to answer tricky state questions. Potion inventory, room progress, checkpoints, and weekly resets all need to agree between the browser and the server. Time boundaries add another wrinkle: a week should reset at local midnight, not at UTC midnight, or players can lose progress at an unexpected hour. We centralized the balance rules and kept the optional classifier out of the gameplay path so a slow or unavailable model cannot block a quest or break a demo.

Combat balance is still a work in progress. We made the numbers easy to tune, but the game needs more playtesting to make preparation meaningful without making fights feel impossible when a player arrives without potions. The visuals are also an honest prototype: the pixel-art textures are drawn in code and are a clear opportunity for polish.

## Accomplishments that we're proud of

- We turned a to-do list into a complete prepare-then-fight loop, with a shared weekly dungeon rather than a map that simply mirrors each player's task list.
- We built a playable Phaser dungeon with 12 rooms, multiple enemy tiers, turn-based combat, four potion effects, checkpoints, and weekly progress.
- We made the reward system server-authoritative: potion amounts come from quest type, and available inventory is recalculated from completion and use records instead of being accepted from the client.
- We made task categorization resilient. Keyword rules work offline, and an optional model can refine the potion choice without controlling the reward amount.
- We kept social accountability in the product through friends, a timestamped activity log, and entry flagging.
- We brought balance values into one place so the team can iterate on the game without rewriting its rules in multiple layers.

## What we learned

We learned that gamification works best when it changes the relationship between the real-world task and the game, not just the decoration around a checkbox. Moving from locked doors to preparation made the central idea clearer and gave quests a purpose inside combat.

We also learned to be precise about trust. We cannot prove that a user completed a real-world task, so we should not claim to prevent cheating. What we can do is timestamp the activity, preserve its history, make rewards server-controlled, and let a player's party see the same record.

Finally, we learned that seemingly small game features depend on careful backend decisions. Time zones, weekly boundaries, retries, potion use, and checkpoints all affect what a player believes the game remembers. Making those rules explicit early made the prototype easier to change as the design evolved.

## What's next for Task Dungeon

Next, we want to deploy the app at **mylost.tech**, test the complete flow with real players, and tune the enemy and potion balance with the team. We also want to replace the placeholder art, make the experience comfortable on phones, and keep improving the first-time experience so a new player can get from creating a quest to entering a battle quickly.

The bigger question is how to make the shared world feel more alive without losing the project's core promise: the dungeon should be powered by what players do in real life. Co-op encounters and more expressive item effects are promising directions, but the next step is to make the current loop dependable, readable, and fun to return to.
