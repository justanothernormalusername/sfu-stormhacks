// Task Dungeon — Phaser client. It only renders and asks the API. Every potion
// award, every clear, and every HP change is decided server-side
// (see src/app/game.py and src/app/routes/api.py).
//
// Balance numbers are NOT duplicated here. The server publishes them at
// /api/config and they land in CFG, so changing a number in src/app/config.py
// moves the whole game. The literals below are layout and pixel art only.

const T = 32; // tile size in px
const ROOM_W = 6; // tiles per room column, including one shared wall
const ENTRANCE = 4; // hallway tiles before the first room column
const ROWS = 15;
const HALL_ROW = 7; // middle row of the 3-tile hallway (rows 6-8)
const FONT = '"Press Start 2P", monospace';
const TIER_COLOR = { mob: "#7bd389", "mini-boss": "#e5986b", boss: "#b28cf0" };
const POTION_COLOR = { heal: "#7bd389", damage: "#e56b6f", haste: "#f2c14e", shield: "#4ea8de" };

let CFG = null; // balance numbers from /api/config, fetched in BootScene

function potionShort(category) {
  return CFG?.potion_effects?.[category]?.short ?? category;
}

// --- HUD (plain DOM above the canvas, not Phaser text) ---
function updateHud(p) {
  document.getElementById("hud-hp").textContent = `${p.hp}/${p.max_hp}`;
  document.getElementById("hp-fill").style.width = `${(100 * p.hp) / p.max_hp}%`;
  document.getElementById("hud-atk").textContent = p.atk;
  document.getElementById("hud-def").textContent = p.defense;
  document.getElementById("hud-depth").textContent = p.checkpoint + 1;

  const box = document.getElementById("hud-items");
  box.replaceChildren();
  const held = CFG.potion_categories.filter((c) => (p.potions?.[c] || 0) > 0);
  if (held.length === 0) {
    box.append(el("span", { class: "muted" }, "No potions — finish a quest to restock"));
    return;
  }
  for (const category of held) {
    box.append(
      el(
        "span",
        { class: "potion", style: `border-color:${POTION_COLOR[category]};color:${POTION_COLOR[category]}` },
        `${potionShort(category)} ×${p.potions[category]}`,
      ),
    );
  }
}

// --- Placeholder pixel art, generated at boot so no asset downloads are needed. ---
function texture(scene, key, w, h, draw) {
  const g = scene.make.graphics({ x: 0, y: 0, add: false });
  draw(g);
  g.generateTexture(key, w, h);
  g.destroy();
}

function makeTextures(scene) {
  texture(scene, "floor", T, T, (g) => {
    g.fillStyle(0x2b2238).fillRect(0, 0, T, T);
    g.fillStyle(0x342a44).fillRect(2, 2, 3, 3).fillRect(20, 14, 2, 2).fillRect(10, 24, 3, 2);
  });
  texture(scene, "hall", T, T, (g) => {
    g.fillStyle(0x221b2d).fillRect(0, 0, T, T);
    g.lineStyle(1, 0x2c2339).strokeRect(0.5, 0.5, T - 1, T - 1);
  });
  texture(scene, "wall", T, T, (g) => {
    g.fillStyle(0x3b3049).fillRect(0, 0, T, T);
    g.fillStyle(0x54466a);
    for (let row = 0; row < 4; row++) {
      const offset = row % 2 ? 8 : 0;
      for (let x = -offset; x < T; x += 16) g.fillRect(x + 1, row * 8 + 1, 14, 6);
    }
  });
  texture(scene, "archway", T, T, (g) => {
    g.fillStyle(0x120d18).fillRect(0, 0, T, T);
    g.lineStyle(3, 0x6b4226).strokeRect(1.5, 1.5, T - 3, T - 3);
  });
  texture(scene, "hero", 24, 28, (g) => {
    g.fillStyle(0x9aa5b1).fillRect(5, 0, 14, 5); // helmet
    g.fillStyle(0xf1c27d).fillRect(6, 4, 12, 7); // face
    g.fillStyle(0x000000).fillRect(9, 6, 2, 2).fillRect(14, 6, 2, 2);
    g.fillStyle(0x4ea8de).fillRect(5, 11, 14, 11); // armor
    g.fillStyle(0xf2c14e).fillRect(5, 15, 14, 2); // belt
    g.fillStyle(0xdcdcdc).fillRect(20, 3, 3, 15); // sword
    g.fillStyle(0x8b5a2b).fillRect(19, 17, 5, 2);
    g.fillStyle(0x2d2d3a).fillRect(6, 22, 5, 6).fillRect(13, 22, 5, 6); // legs
  });
  texture(scene, "enemy_mob", 28, 22, (g) => {
    g.fillStyle(0x7bd389).fillEllipse(14, 13, 28, 18);
    g.fillStyle(0x5bb36b).fillEllipse(14, 17, 24, 8);
    g.fillStyle(0xffffff).fillCircle(9, 10, 3).fillCircle(19, 10, 3);
    g.fillStyle(0x000000).fillCircle(10, 10, 1.5).fillCircle(20, 10, 1.5);
  });
  texture(scene, "enemy_mini-boss", 36, 36, (g) => {
    g.fillStyle(0xeeeeee).fillTriangle(4, 10, 9, 0, 12, 10).fillTriangle(24, 10, 27, 0, 32, 10); // horns
    g.fillStyle(0xd96c6c).fillRoundedRect(3, 8, 30, 26, 6);
    g.fillStyle(0xffe66d).fillRect(9, 15, 5, 4).fillRect(22, 15, 5, 4);
    g.fillStyle(0x7a2e2e).fillRect(10, 25, 16, 4);
    g.fillStyle(0xffffff).fillRect(12, 25, 3, 3).fillRect(21, 25, 3, 3);
  });
  texture(scene, "enemy_boss", 56, 52, (g) => {
    g.fillStyle(0x6a3fb5).fillTriangle(0, 30, 14, 10, 18, 34).fillTriangle(56, 30, 42, 10, 38, 34); // wings
    g.fillStyle(0x9b5de5).fillRoundedRect(12, 10, 32, 40, 10);
    g.fillStyle(0xf2c14e).fillTriangle(16, 12, 20, 0, 24, 12).fillTriangle(32, 12, 36, 0, 40, 12); // horns
    g.fillStyle(0xff4d4d).fillRect(19, 20, 6, 5).fillRect(31, 20, 6, 5);
    g.fillStyle(0x3d1f6b).fillRect(20, 36, 16, 5);
    g.fillStyle(0xffffff).fillTriangle(21, 36, 23, 41, 25, 36).fillTriangle(31, 36, 33, 41, 35, 36);
  });
  texture(scene, "chest", 26, 20, (g) => {
    g.fillStyle(0x8b5a2b).fillRect(0, 4, 26, 16);
    g.fillStyle(0x6b4226).fillRect(0, 0, 26, 6);
    g.fillStyle(0xf2c14e).fillRect(0, 8, 26, 2).fillRect(11, 6, 4, 6);
  });
  texture(scene, "spark", 4, 4, (g) => g.fillStyle(0xffffff).fillRect(0, 0, 4, 4));
}

// --- Scenes ---
class BootScene extends Phaser.Scene {
  constructor() {
    super("boot");
  }

  init(data) {
    // A room index means "wake up here" (a checkpoint return); a point means a
    // raw position (only the entry hallway uses that).
    this.spawnRoom = data?.spawnRoom;
    this.spawnPoint = data?.spawnPoint;
  }

  create() {
    if (!this.textures.exists("floor")) makeTextures(this);
    const loading = this.add.text(20, 20, "Loading dungeon...", { fontFamily: FONT, fontSize: "12px" });
    // `/api/rooms` returns the whole floor — rooms, the tile grid, and the
    // corridor links — not a bare array. The client renders it and nothing more.
    Promise.all([api("/api/rooms"), api("/api/player"), api("/api/config")])
      .then(([floor, player, config]) => {
        CFG = config;
        updateHud(player);
        this.scene.start("dungeon", { floor, player, spawnRoom: this.spawnRoom, spawnPoint: this.spawnPoint });
      })
      .catch((err) => loading.setText(`Could not load the dungeon: ${err.message}`));
  }
}

class DungeonScene extends Phaser.Scene {
  constructor() {
    super("dungeon");
  }

  init(data) {
    this.floor = data.floor;
    this.rooms = data.floor.rooms;
    this.stats = data.player;
    this.spawnRoom = data.spawnRoom;
    this.spawnPoint = data.spawnPoint;
  }

  create() {
    const cols = Math.max(1, Math.ceil(this.rooms.length / 2));
    const width = ENTRANCE + ROOM_W * cols + 1;
    const grid = this.buildGrid(width, cols);
    this.walls = this.physics.add.staticGroup();

    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < width; x++) {
        const cell = grid[y][x];
        const px = x * T + T / 2;
        const py = y * T + T / 2;
        if (cell === "#") this.walls.create(px, py, "wall");
        else if (cell === "h") this.add.image(px, py, "hall");
        else if (cell === "f") this.add.image(px, py, "floor");
      }
    }

    this.hero = this.physics.add.sprite(0, 0, "hero").setDepth(10);
    this.hero.body.setSize(16, 12).setOffset(4, 16);
    // Room geometry is needed before buildRoom runs (a checkpoint return has to
    // drop the hero inside that room), so it comes from this helper, not from
    // the centre the rooms cache as they are drawn.
    const room = this.spawnRoom !== undefined ? this.roomCenter(this.spawnRoom) : null;
    const start = room ?? this.spawnPoint ?? { x: 2 * T, y: HALL_ROW * T + T / 2 };
    this.hero.setPosition(start.x, start.y);
    this.physics.add.collider(this.hero, this.walls);

    this.rooms.forEach((r, i) => this.buildRoom(r, i));

    const worldW = width * T;
    const worldH = ROWS * T;
    this.physics.world.setBounds(0, 0, worldW, worldH);
    const zoom = this.scale.height / worldH;
    // Small dungeons are narrower than the screen: widen the bounds so the map sits centered.
    const viewW = this.scale.width / zoom;
    const padX = Math.max(0, (viewW - worldW) / 2);
    this.cameras.main.setBounds(-padX, 0, worldW + 2 * padX, worldH).setZoom(zoom);
    this.cameras.main.startFollow(this.hero, true, 0.15, 0.15);

    this.hint = this.add
      .text(this.scale.width / 2, this.scale.height - 16, "", {
        fontFamily: FONT, fontSize: "10px", color: "#ffffff", backgroundColor: "#000000aa", padding: { x: 8, y: 6 },
      })
      .setOrigin(0.5, 1).setScrollFactor(0).setDepth(100);
    // The HUD text must ignore camera zoom, so draw it with a second, unzoomed camera.
    this.cameras.main.ignore(this.hint);
    const uiCam = this.cameras.add(0, 0, this.scale.width, this.scale.height);
    uiCam.ignore(this.children.list.filter((obj) => obj !== this.hint));

    this.keys = this.input.keyboard.addKeys("W,A,S,D,UP,DOWN,LEFT,RIGHT");
    this.inBattle = false;
  }

  buildGrid(width, cols) {
    // The layout comes from the server's room list, so every player walks the
    // same weekly dungeon. Two rooms per column, top and bottom, off one hallway.
    const grid = Array.from({ length: ROWS }, () => Array(width).fill(" "));
    const box = (x0, y0, x1, y1, fill) => {
      for (let y = y0; y <= y1; y++) {
        for (let x = x0; x <= x1; x++) {
          const edge = y === y0 || y === y1 || x === x0 || x === x1;
          if (edge) grid[y][x] = grid[y][x] === " " ? "#" : grid[y][x];
          else grid[y][x] = fill;
        }
      }
    };
    box(0, 5, width - 1, 9, "h"); // hallway
    for (let c = 0; c < cols; c++) {
      const x0 = ENTRANCE + ROOM_W * c;
      for (const top of [true, false]) {
        const index = 2 * c + (top ? 0 : 1);
        if (index >= this.rooms.length) continue;
        if (top) box(x0, 0, x0 + ROOM_W, 5, "f");
        else box(x0, 9, x0 + ROOM_W, ROWS - 1, "f");
      }
    }
    return grid;
  }

  // Where room `i` sits on the map. Pure geometry, so it is available before
  // anything is drawn and is the single source of truth for spawn points.
  roomCenter(i) {
    const top = i % 2 === 0;
    return {
      x: (ENTRANCE + ROOM_W * Math.floor(i / 2) + 3) * T + T / 2,
      y: (top ? 3 : 12) * T + 8,
    };
  }

  buildRoom(room, i) {
    const col = Math.floor(i / 2);
    const top = i % 2 === 0;
    const centerX = (ENTRANCE + ROOM_W * col + 3) * T + T / 2;
    const centerY = (top ? 3 : 12) * T;
    const enemyY = centerY + 8;
    room.center = { x: centerX, y: enemyY };

    // Open archway tile on the hallway wall — decorative only. There is no
    // collider here and none is wanted: every room is enterable from the start.
    const doorX = (ENTRANCE + ROOM_W * col + 3) * T + T / 2;
    const doorY = (top ? 5 : 9) * T + T / 2;
    this.walls.getChildren()
      .filter((w) => w.x === doorX && w.y === doorY)
      .forEach((w) => w.destroy());
    this.add.image(doorX, doorY, "archway");

    // Three things can be in a room, and the branch order matters: a safe room
    // has no `enemy` at all (so touching room.enemy.tier above would crash on
    // the entrance, which is room 0), and a blocked room is one the server has
    // not unlocked yet, so it must not be walkable-into either.
    const labelY = (top ? 1 : 10) * T + 2;
    this.add
      .text(centerX, labelY, room.name, {
        fontFamily: FONT, fontSize: "8px",
        color: room.blocked ? "#6b5f7d" : TIER_COLOR[room.enemy?.tier],
        align: "center", wordWrap: { width: (ROOM_W - 1) * T - 8 },
      })
      .setOrigin(0.5, 0);

    if (room.safe) {
      // The shrine is a chest you may use once; the entrance is just a room.
      this.add.image(centerX, enemyY, room.restore ? "chest" : "archway");
      this.add.text(centerX, centerY + 26, room.cleared ? "SPENT" : room.restore ? "REST" : "SAFE", {
        fontFamily: FONT, fontSize: "8px", color: room.cleared ? "#6b5f7d" : "#7bd389",
      }).setOrigin(0.5, 0);
      if (room.restore && !room.cleared) {
        const shrine = this.physics.add.staticImage(centerX, enemyY, "chest");
        this.physics.add.overlap(this.hero, shrine, () => this.useShrine(room));
      }
      return;
    }

    if (room.blocked) {
      // Sealed: drawn, walkable around, but not enterable. The door out of the
      // previous room is what opens it, and only the server decides that.
      this.add.image(centerX, enemyY, "archway").setAlpha(0.25);
      this.add.text(centerX, centerY + 26, "SEALED", {
        fontFamily: FONT, fontSize: "8px", color: "#6b5f7d",
      }).setOrigin(0.5, 0);
      return;
    }

    if (room.cleared) {
      this.add.image(centerX, enemyY, "chest");
      this.add.text(centerX, centerY + 26, "CLEARED", { fontFamily: FONT, fontSize: "8px", color: "#7bd389" })
        .setOrigin(0.5, 0);
    } else {
      const enemy = this.physics.add.staticImage(centerX, enemyY, `enemy_${room.enemy.tier}`);
      this.tweens.add({ targets: enemy, y: enemy.y - 4, duration: 600, yoyo: true, repeat: -1 });
      this.physics.add.overlap(this.hero, enemy, () => this.startBattle(room));
    }

    if (room.index === this.stats.checkpoint && this.stats.checkpoint > 0) {
      this.add.text(centerX, centerY + 40, "▲ CHECKPOINT", { fontFamily: FONT, fontSize: "7px", color: "#4ea8de" })
        .setOrigin(0.5, 0);
    }
  }

  // Resting is a server action like any other. The client does not decide that
  // HP is full afterwards — it asks, and redraws the number the server sends.
  async useShrine(room) {
    if (this.busy) return;
    this.busy = true;
    try {
      const result = await api(`/api/rooms/${room.index}/enter`, { method: "POST" });
      this.stats = result.player;
      updateHud(this.stats);
      this.hint.setText(result.restored ? `The shrine restores you. +${result.restored} HP.` : "");
      this.time.delayedCall(600, () => {
        // Reload the floor so the shrine redraws as SPENT and the newly-opened
        // doors behind it appear, rather than guessing at that here.
        this.scene.start("boot", { spawnRoom: room.index });
      });
    } catch (err) {
      this.hint.setText(err.message);
      this.busy = false;
    }
  }

  startBattle(room) {
    if (this.inBattle) return;
    this.inBattle = true;
    this.cameras.main.flash(250, 255, 255, 255);
    this.time.delayedCall(250, () =>
      this.scene.start("battle", { room, player: this.stats, spawnRoom: room.index }));
  }

  update() {
    const k = this.keys;
    const speed = 150;
    const vx = (k.LEFT.isDown || k.A.isDown ? -1 : 0) + (k.RIGHT.isDown || k.D.isDown ? 1 : 0);
    const vy = (k.UP.isDown || k.W.isDown ? -1 : 0) + (k.DOWN.isDown || k.S.isDown ? 1 : 0);
    const len = Math.hypot(vx, vy) || 1;
    this.hero.setVelocity((vx / len) * speed, (vy / len) * speed);
    if (vx) this.hero.setFlipX(vx < 0);

    // Standing near an undefended room describes what is waiting inside it.
    const near = this.rooms.find(
      (r) => r.center && Phaser.Math.Distance.Between(this.hero.x, this.hero.y, r.center.x, r.center.y) < T * 1.8,
    );
    let hint = "";
    if (near && !near.cleared) {
      // Safe rooms have no enemy and blocked ones are not enterable, so this is
      // three cases — reading near.enemy unconditionally crashed on room 0.
      if (near.safe) hint = near.restore ? `${near.name} — a shrine. Walk in to rest.` : `${near.name} — safe ground.`;
      else if (near.blocked) hint = `${near.name} — sealed. Clear the rooms leading here.`;
      else hint = `${near.name} — a ${near.enemy.name} (${near.enemy.hp} HP, ${near.enemy.atk} ATK). Walk in to fight.`;
    }
    this.hint.setText(hint).setVisible(Boolean(hint));
  }
}

class BattleScene extends Phaser.Scene {
  constructor() {
    super("battle");
  }

  init(data) {
    this.room = data.room;
    this.stats = data.player;
    this.spawnRoom = data.spawnRoom;
    // Captured before the fight: a defeat has to send you back to where you
    // started this attempt, not to a checkpoint this fight would have set.
    this.entryCheckpoint = this.stats.checkpoint;
  }

  create() {
    const { width, height } = this.scale;
    const enemy = this.room.enemy;
    // Open the fight on the server first. Everything below draws the response:
    // enemy HP, the HP you walked in with, cooldowns. If the server refuses —
    // someone else cleared the room, or it is sealed — there is no fight to
    // draw, so we bail back to the map rather than showing a fight that the
    // server does not consider to exist.
    // `api` is the module-level helper, not a scene method — calling this.api()
    // here was a TypeError the moment you walked into a fight.
    api(`/api/rooms/${this.room.index}/enter`, { method: "POST" })
      .then((result) => {
        if (result.safe) {
          // A safe room never reaches here (the map handles shrines), but if it
          // does, there is nothing to fight and going back is the honest answer.
          this.scene.start("boot", { spawnRoom: this.room.index });
          return;
        }
        this.drawBattle(result.fight, enemy);
      })
      .catch((err) => this.failedToStart(err));
  }

  // The server refused to open the fight — sealed, already cleared, or offline.
  failedToStart(err) {
    this.add.text(this.scale.width / 2, this.scale.height / 2,
      `Cannot enter: ${err.message}\n\nPress SPACE to go back.`, {
        fontFamily: FONT, fontSize: "12px", color: "#e56b6f", align: "center",
      }).setOrigin(0.5);
    this.over = true;
    this.result = "error";
    this.settling = false;
    // The key handlers normally live at the end of drawBattle, which never ran —
    // so without this the message is a lie: SPACE would do nothing and the
    // player would be stuck on this screen until they reloaded the page.
    this.input.keyboard.on("keydown-SPACE", () => this.finish());
  }

  drawBattle(fight, enemy) {
    const { width, height } = this.scale;
    this.fight = fight;
    this.heroHp = fight.hero.hp;
    this.enemyHp = fight.enemy.hp;
    this.powerCooldown = fight.power_cd;
    this.defending = fight.defended;
    this.busy = false;
    this.over = false;
    // True while a win/lose write is in flight, so SPACE cannot skip ahead of it.
    this.settling = false;
    // Buff timers live in the server's state, not here. `this.buffs` used to be a
    // client-side countdown that could disagree with the fight it was describing.
    this.buffs = { ...(fight.buffs || {}) };

    this.add.rectangle(0, 0, width, height, 0x120d18).setOrigin(0);
    this.add.rectangle(0, height * 0.62, width, height * 0.38, 0x241c31).setOrigin(0);
    this.add.text(width / 2, 24, `${enemy.tier.toUpperCase()}: ${enemy.name}`, {
      fontFamily: FONT, fontSize: "16px", color: TIER_COLOR[enemy.tier],
    }).setOrigin(0.5, 0);
    this.add.text(width / 2, 52, this.room.name, {
      fontFamily: FONT, fontSize: "9px", color: "#9d90b3",
    }).setOrigin(0.5, 0);

    this.heroSprite = this.add.image(width * 0.25, height * 0.45, "hero").setScale(4);
    const enemyScale = { mob: 5, "mini-boss": 4.5, boss: 3.4 }[enemy.tier];
    this.enemySprite = this.add.image(width * 0.72, height * 0.42, `enemy_${enemy.tier}`).setScale(enemyScale);
    this.tweens.add({ targets: this.enemySprite, y: this.enemySprite.y - 8, duration: 700, yoyo: true, repeat: -1 });

    this.heroBar = this.makeBar(width * 0.25, height * 0.62 - 28, this.stats.username);
    this.enemyBar = this.makeBar(width * 0.72, height * 0.62 - 28, enemy.name);
    this.buffLine = this.add.text(width / 2, height * 0.62 - 44, "", {
      fontFamily: FONT, fontSize: "8px", color: "#f2c14e",
    }).setOrigin(0.5, 0);
    this.refreshBars();

    this.message = this.add.text(32, height * 0.62 + 18, "", {
      fontFamily: FONT, fontSize: "11px", color: "#ece6f5", wordWrap: { width: width - 64 }, lineSpacing: 6,
    });

    this.menu = this.add.container(32, height - 64);
    this.buttons = ["1 Attack", "2 Power Strike", "3 Defend", "Esc Flee"].map((label, i) => {
      const btn = this.add.text(i * 220, 0, label, {
        fontFamily: FONT, fontSize: "11px", color: "#1a1424", backgroundColor: "#f2c14e", padding: { x: 10, y: 8 },
      }).setInteractive({ useHandCursor: true });
      btn.on("pointerdown", () => this.choose(["attack", "power", "defend", "flee"][i]));
      this.menu.add(btn);
      return btn;
    });

    const kb = this.input.keyboard;
    kb.on("keydown-ONE", () => this.choose("attack"));
    kb.on("keydown-TWO", () => this.choose("power"));
    kb.on("keydown-THREE", () => this.choose("defend"));
    kb.on("keydown-ESC", () => this.choose("flee"));
    kb.on("keydown-SPACE", () => this.choose("continue"));
    // Potion slots are keys 4..7 and are rebuilt as the inventory changes, so
    // the handler looks the category up by position rather than capturing one.
    kb.on("keydown", (event) => {
      const K = Phaser.Input.Keyboard.KeyCodes;
      const index = [K.FOUR, K.FIVE, K.SIX, K.SEVEN].indexOf(event.keyCode);
      const category = this.heldPotions()[index];
      if (category) this.choose(`potion:${category}`);
    });

    this.say(`A wild ${enemy.name} blocks the way. It hits for about ${enemy.atk}.`);
    this.refresh();
  }

  heldPotions() {
    return CFG.potion_categories.filter((c) => (this.stats.potions?.[c] || 0) > 0);
  }

  makeBar(x, y, name) {
    this.add.text(x, y - 18, name, { fontFamily: FONT, fontSize: "9px" }).setOrigin(0.5, 0);
    this.add.rectangle(x, y + 6, 204, 16, 0x0b0810).setStrokeStyle(2, 0x3d3052);
    const fill = this.add.rectangle(x - 100, y + 6, 200, 12, 0xe56b6f).setOrigin(0, 0.5);
    const label = this.add.text(x, y + 18, "", { fontFamily: FONT, fontSize: "8px", color: "#9d90b3" })
      .setOrigin(0.5, 0);
    return { fill, label };
  }

  refreshBars() {
    const set = (bar, hp, max) => {
      bar.fill.width = Math.max(0, (200 * hp) / max);
      bar.label.setText(`${Math.max(0, hp)} / ${max}`);
    };
    set(this.heroBar, this.fight.hero.hp, this.fight.hero.max_hp);
    set(this.enemyBar, this.fight.enemy.hp, this.fight.enemy.max_hp);
    const active = Object.entries(this.fight.buffs || {}).filter(([, turns]) => turns > 0);
    this.buffLine.setText(active.map(([k, t]) => `${potionShort(k)} ${t}`).join("  "));
  }

  // Rebuild the potion row from the current inventory. The server is the only
  // thing that decides what is left; this just draws what it last told us.
  renderPotions() {
    if (this.potionRow) this.potionRow.destroy();
    this.potionRow = this.add.container(32, this.scale.height - 112);
    const held = this.heldPotions();
    if (!held.length) {
      this.potionRow.add(this.add.text(0, 0, "No potions — finish a quest on the Quest Board to restock", {
        fontFamily: FONT, fontSize: "9px", color: "#9d90b3",
      }));
      return;
    }
    held.forEach((category, i) => {
      const btn = this.add.text(i * 160, 0, `${i + 4} ${potionShort(category)} ×${this.stats.potions[category]}`, {
        fontFamily: FONT, fontSize: "9px", color: "#1a1424",
        backgroundColor: POTION_COLOR[category], padding: { x: 8, y: 7 },
      }).setInteractive({ useHandCursor: true });
      btn.on("pointerdown", () => this.choose(`potion:${category}`));
      this.potionRow.add(btn);
    });
  }

  refresh() {
    this.buttons[1].setText(this.powerCooldown ? `2 Power (${this.powerCooldown})` : "2 Power Strike");
    this.buttons[1].setAlpha(this.powerCooldown ? 0.5 : 1);
    this.menu.setVisible(!this.over);
    this.renderPotions();
    if (this.potionRow) this.potionRow.setVisible(!this.over);
    // Once the fight is over the menu is hidden, so the only thing left to say is
    // that SPACE continues. Fleeing in particular resolves without a win or a
    // loss message, and without this the player is left staring at a dead screen
    // not knowing whether the key still works.
    if (this.over && !this.message.text.includes("Press SPACE")) {
      this.say(`${this.message.text}\n\nPress SPACE to continue.`);
    }
    this.refreshBars();
  }

  say(text) {
    this.message.setText(text);
  }

  floatText(x, y, text, color) {
    const t = this.add.text(x, y, text, { fontFamily: FONT, fontSize: "18px", color, stroke: "#000", strokeThickness: 4 })
      .setOrigin(0.5);
    this.tweens.add({ targets: t, y: y - 50, alpha: 0, duration: 900, onComplete: () => t.destroy() });
  }

  hitEffect(target) {
    this.tweens.add({ targets: target, x: target.x + 10, duration: 50, yoyo: true, repeat: 3 });
    target.setTint(0xff6666);
    this.time.delayedCall(250, () => target.clearTint());
  }

  // Local damage simulation is deliberately gone. `roll()` and `strike()` used to
  // compute crits and damage with Math.random() in the browser, which is precisely
  // the thing that made the server's balance numbers decorative — and which let a
  // player post whatever HP they liked. Damage now comes from game.fight_step, and
  // `tickBuffs()` went with it: buff expiry is the reducer's bookkeeping, so a
  // second client-side countdown could only ever contradict the real fight.

  // The server owns the fight. `this.fight` is its state, mirrored verbatim
  // only so it can be drawn; every number on screen came from a response to
  // POST /api/rooms/{id}/act, and none of it was computed in this file.
  async choose(action) {
    if (action === "continue") return this.finish();
    // Fleeing is free server-side, but it still goes through the API so the
    // fight is closed out rather than left dangling.
    if (action === "flee") return this.act("flee");
    if (this.busy || this.over) return;
    if (action.startsWith("potion:")) return this.act("potion", action.slice("potion:".length));
    return this.act(action);
  }

  async act(action, potion = null) {
    if (this.busy || this.over) return;
    this.busy = true;
    try {
      const result = await api(`/api/rooms/${this.room.index}/act`, {
        method: "POST",
        body: { action, potion },
      });
      this.applyFight(result);
      // The server already knows the fight is over. Fleeing resolves as "fled",
      // which carries no `resolved` block because nothing was earned or lost —
      // so it needs handling separately from a win or a defeat.
      if (this.fight.state === "fled") {
        this.over = true;
        this.result = "fled";
        return this.refresh();
      }
      if (result.resolved?.cleared) this.win();
      else if (result.resolved && !result.resolved.cleared) this.lose();
    } catch (err) {
      // The server refused the action — a power strike on cooldown, or a potion
      // already spent. Say so and hand the turn back without punishing.
      this.say(err.message);
      this.busy = false;
    }
  }

  // Mirror the server's state and narrate the lines it appended this turn.
  // `log` is the server's own prose, so the client cannot drift from it.
  applyFight(result) {
    const before = this.fight;
    this.fight = result.fight;
    this.stats = result.player;

    const added = this.fight.log.slice((before?.log || []).length);
    this.say(added.join("\n"));
    if (added.length) {
      const heroDamage = this.fight.hero.hp < (before?.hero.hp ?? this.fight.hero.hp);
      const enemyDamage = (this.fight.enemy?.hp ?? 0) < (before?.enemy?.hp ?? 0);
      if (enemyDamage) this.hitEffect(this.enemySprite);
      if (heroDamage) {
        this.hitEffect(this.heroSprite);
        this.cameras.main.shake(150, 0.006);
      }
    }

    this.powerCooldown = this.fight.power_cd;
    this.buffs = { ...(this.fight.buffs || {}) };
    this.busy = false;
    this.refresh();
    updateHud(this.stats);
  }

  // A win is already recorded: `act` returned `resolved`, because the same
  // response that killed the enemy wrote the clear row. So there is no second
  // "claim your reward" call to make — and no window in which a player could
  // claim one without having fought.
  win() {
    this.over = true;
    this.result = "won";
    this.settling = true;
    this.refresh();
    this.tweens.killTweensOf(this.enemySprite);
    this.tweens.add({ targets: this.enemySprite, alpha: 0, scale: 0, angle: 180, duration: 600 });
    this.add.particles(this.enemySprite.x, this.enemySprite.y, "spark", {
      speed: { min: 80, max: 260 }, lifespan: 700, quantity: 40, tint: [0xf2c14e, 0xffffff, 0xe56b6f], emitting: false,
    }).explode(40);
    const checkpoint = this.stats.checkpoint;
    this.say(`Victory! ${this.room.name} is yours.\nRoom ${checkpoint + 1} cleared this week.\n\nPress SPACE to continue.`);
    this.floatText(this.scale.width / 2, this.scale.height * 0.3, `ROOM ${checkpoint + 1}`, "#f2c14e");
    this.settling = false;
  }

  // A loss is also already recorded by `act`: the potions drunk this fight are
  // spent and the checkpoint row has been rewritten to full, which is what
  // "you wake up healed" means. The client only narrates it.
  lose() {
    this.over = true;
    this.result = "lost";
    this.settling = true;
    this.refresh();
    this.tweens.add({ targets: this.heroSprite, alpha: 0.3, angle: -90, duration: 500 });
    const checkpoint = this.entryCheckpoint;
    const where = checkpoint > 0 ? `Room ${checkpoint + 1}` : "the entrance hall";
    this.say(`You fall.\n\nYou wake at ${where}, fully healed. The potions you drank are spent.\n\nPress SPACE to continue.`);
    this.settling = false;
  }

  finish() {
    // Wait for the win/lose write to land, or the next scene loads stale HP.
    if (!this.over || !this.result || this.settling) return;
    if (this.result === "lost") return this.scene.start("boot", { spawnRoom: this.entryCheckpoint });
    if (this.result === "error") return this.scene.start("boot", { spawnRoom: this.spawnRoom });
    if (this.result === "fled") return this.scene.start("boot", { spawnRoom: this.spawnRoom });
    this.scene.start("boot", { spawnRoom: this.room.index });
  }
}

document.fonts.load(`12px ${FONT}`).finally(() => {
  window.game = new Phaser.Game({ // exposed for debugging in the browser console
    type: Phaser.AUTO,
    parent: "game",
    width: 960,
    height: 540,
    pixelArt: true,
    backgroundColor: "#0b0810",
    physics: { default: "arcade" },
    scene: [BootScene, DungeonScene, BattleScene],
  });
});