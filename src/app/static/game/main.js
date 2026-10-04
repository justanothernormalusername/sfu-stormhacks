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
    Promise.all([api("/api/rooms"), api("/api/player"), api("/api/config")])
      .then(([rooms, player, config]) => {
        CFG = config;
        updateHud(player);
        this.scene.start("dungeon", { rooms, player, spawnRoom: this.spawnRoom, spawnPoint: this.spawnPoint });
      })
      .catch((err) => loading.setText(`Could not load the dungeon: ${err.message}`));
  }
}

class DungeonScene extends Phaser.Scene {
  constructor() {
    super("dungeon");
  }

  init(data) {
    this.rooms = data.rooms;
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

    const labelY = (top ? 1 : 10) * T + 2;
    this.add
      .text(centerX, labelY, room.name, {
        fontFamily: FONT, fontSize: "8px", color: TIER_COLOR[room.enemy.tier], align: "center",
        wordWrap: { width: (ROOM_W - 1) * T - 8 },
      })
      .setOrigin(0.5, 0);

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
      hint = `${near.name} — a ${near.enemy.name} (${near.enemy.hp} HP, ${near.enemy.atk} ATK). Walk in to fight.`;
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
    this.enemyHp = enemy.hp;
    this.heroHp = this.stats.hp;
    this.powerCooldown = 0;
    this.defending = false;
    this.busy = false;
    this.over = false;
    // True while a win/lose write is in flight, so SPACE cannot skip ahead of it.
    this.settling = false;
    this.buffs = { damage: 0, haste: 0, shield: 0 };

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
    set(this.heroBar, this.heroHp, this.stats.max_hp);
    set(this.enemyBar, this.enemyHp, this.room.enemy.hp);
    const active = Object.entries(this.buffs).filter(([, turns]) => turns > 0);
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

  roll() {
    const [low, high] = CFG.damage_variance;
    return Phaser.Math.FloatBetween(low, high);
  }

  // One attack. Returns the damage dealt so the caller can narrate it.
  strike(power) {
    const crit = Math.random() < CFG.crit_chance;
    const rage = this.buffs.damage > 0 ? CFG.potion_effects.damage.mult : 1;
    const dmg = Math.max(
      CFG.min_damage,
      Math.round(
        this.stats.atk * this.roll() * (power ? CFG.power_mult : 1) * rage * (crit ? CFG.crit_mult : 1),
      ),
    );
    this.enemyHp -= dmg;
    this.hitEffect(this.enemySprite);
    this.floatText(this.enemySprite.x, this.enemySprite.y - 60, `-${dmg}`, crit ? "#f2c14e" : "#ffffff");
    return { dmg, crit };
  }

  tickBuffs() {
    // One player action = one turn of each active buff.
    for (const key of Object.keys(this.buffs)) {
      if (this.buffs[key] > 0) this.buffs[key]--;
    }
  }

  choose(action) {
    if (action === "continue") return this.finish();
    if (action === "flee" && (!this.busy || this.over)) return this.leave();
    if (this.busy || this.over) return;
    if (action.startsWith("potion:")) return this.drink(action.slice("potion:".length));
    if (action === "power" && this.powerCooldown) return this.say("Power Strike is still recharging!");

    this.busy = true;
    if (this.powerCooldown) this.powerCooldown--;
    let text;
    if (action === "attack" || action === "power") {
      const power = action === "power";
      if (power) this.powerCooldown = CFG.power_cooldown;
      const first = this.strike(power);
      let extra = "";
      if (this.buffs.haste > 0) {
        extra = ` Haste strikes again for ${this.strike(power).dmg}!`;
      }
      text = `${power ? "POWER STRIKE! " : ""}${first.crit ? "Critical hit! " : ""}You deal ${first.dmg} damage.${extra}`;
    } else {
      this.defending = true;
      const heal = Math.min(CFG.defend_heal, this.stats.max_hp - this.heroHp);
      this.heroHp += heal;
      if (heal) this.floatText(this.heroSprite.x, this.heroSprite.y - 70, `+${heal}`, "#7bd389");
      text = `You raise your shield${heal ? ` and recover ${heal} HP` : ""}.`;
    }
    this.tickBuffs();
    this.say(text);
    this.refresh();

    if (this.enemyHp <= 0) return this.time.delayedCall(500, () => this.win());
    this.time.delayedCall(700, () => this.enemyTurn());
  }

  // Drinking takes a turn, so a potion is a real choice and not a free heal.
  async drink(category) {
    this.busy = true;
    const effect = CFG.potion_effects[category];
    try {
      const result = await api(`/api/potions/${category}/use`, {
        method: "POST",
        body: { room_index: this.room.index },
      });
      this.stats.potions = result.potions;
      let text = `You drink ${effect.label}.`;
      if (category === "heal") {
        const healed = Math.min(effect.heal, this.stats.max_hp - this.heroHp);
        this.heroHp += healed;
        text = healed
          ? `You drink ${effect.label} and recover ${healed} HP.`
          : `You drink ${effect.label}, but you are already at full health.`;
        if (healed) this.floatText(this.heroSprite.x, this.heroSprite.y - 70, `+${healed}`, POTION_COLOR.heal);
      } else {
        this.buffs[category] = effect.turns;
        const detail = {
          damage: `Attacks hit ${effect.mult}× harder`,
          haste: "You strike twice each turn",
          shield: `Incoming damage is cut ${Math.round((1 - effect.reduction) * 100)}%`,
        }[category];
        text += ` ${detail} for ${effect.turns} turns.`;
      }
      this.tickBuffs();
      this.say(text);
      updateHud({ ...this.stats, hp: Math.max(0, this.heroHp) });
      this.refresh();
      this.time.delayedCall(700, () => this.enemyTurn());
    } catch (err) {
      // The server rejected the spend — most likely a double-click raced the
      // first request. Say so and hand the turn back without punishing.
      this.say(err.message);
      this.refresh();
      this.busy = false;
    }
  }

  enemyTurn() {
    const enemy = this.room.enemy;
    let dmg = Math.max(CFG.min_damage, Math.round(enemy.atk * this.roll()) - this.stats.defense);
    if (this.defending) dmg = Math.ceil(dmg * CFG.defend_reduction);
    if (this.buffs.shield > 0) dmg = Math.ceil(dmg * CFG.potion_effects.shield.reduction);
    this.defending = false;
    this.heroHp -= dmg;
    this.tweens.add({ targets: this.enemySprite, x: this.enemySprite.x - 40, duration: 120, yoyo: true });
    this.hitEffect(this.heroSprite);
    this.cameras.main.shake(150, 0.006);
    this.floatText(this.heroSprite.x, this.heroSprite.y - 70, `-${dmg}`, "#e56b6f");
    this.say(`${enemy.name} attacks for ${dmg} damage!`);
    this.refresh();
    if (this.heroHp <= 0) return this.lose();
    this.busy = false;
  }

  async win() {
    this.over = true;
    this.result = "won";
    this.settling = true;
    this.refresh();
    this.tweens.killTweensOf(this.enemySprite);
    this.tweens.add({ targets: this.enemySprite, alpha: 0, scale: 0, angle: 180, duration: 600 });
    this.add.particles(this.enemySprite.x, this.enemySprite.y, "spark", {
      speed: { min: 80, max: 260 }, lifespan: 700, quantity: 40, tint: [0xf2c14e, 0xffffff, 0xe56b6f], emitting: false,
    }).explode(40);
    this.say("Victory! Claiming the room...");
    try {
      // HP rides along with the clear: the server derives the next fight's HP
      // from this row, so there is no separate mutable value to drift.
      const result = await api(`/api/rooms/${this.room.index}/clear`, {
        method: "POST",
        body: { hp: this.heroHp },
      });
      this.stats = result.player;
      updateHud(this.stats);
      this.say(`Victory! ${this.room.name} is yours.\nRoom ${result.player.checkpoint + 1} cleared this week.\n\nPress SPACE to continue.`);
      this.floatText(this.scale.width / 2, this.scale.height * 0.3, `ROOM ${result.player.checkpoint + 1}`, "#f2c14e");
    } catch (err) {
      this.say(`Victory... but the clear was refused: ${err.message}\n\nPress SPACE to continue.`);
    }
    this.settling = false;
  }

  // Defeat costs the potions you drank and the room you were standing in, and
  // nothing else. You wake at the checkpoint with full health.
  async lose() {
    this.over = true;
    this.result = "lost";
    this.settling = true;
    this.refresh();
    this.tweens.add({ targets: this.heroSprite, alpha: 0.3, angle: -90, duration: 500 });
    const checkpoint = this.entryCheckpoint;
    let restored = true;
    try {
      // Restores full HP on the checkpoint row. A 404 just means the player has
      // never cleared anything this week, so there is nothing to restore — HP
      // is already full in that case.
      await api(`/api/rooms/${checkpoint}/hp`, { method: "POST", body: { hp: this.stats.max_hp } });
    } catch {
      restored = false;
    }
    const where = checkpoint > 0 ? `Room ${checkpoint + 1}` : "the entrance hall";
    const tail = restored ? ", fully healed" : "";
    this.say(`You fall.\n\nYou wake at ${where}${tail}. The potions you drank are spent.\n\nPress SPACE to continue.`);
    this.settling = false;
  }

  // Fleeing is free and costs nothing but the fight: you come back to the room
  // you walked into, still holding every potion.
  leave() {
    this.scene.start("boot", { spawnRoom: this.spawnRoom });
  }

  finish() {
    // Wait for the win/lose write to land, or the next scene loads stale HP.
    if (!this.over || !this.result || this.settling) return;
    if (this.result === "lost") return this.scene.start("boot", { spawnRoom: this.entryCheckpoint });
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