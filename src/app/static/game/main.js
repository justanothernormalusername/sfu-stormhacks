// Task Dungeon — Phaser client. It only renders and asks the API; every unlock,
// XP grant, and loot roll is decided server-side (see src/app/game.py).

const T = 32; // tile size in px
const ROOM_W = 6; // tiles per room column, including one shared wall
const ENTRANCE = 4; // hallway tiles before the first room column
const ROWS = 15;
const HALL_ROW = 7; // middle row of the 3-tile hallway (rows 6-8)
const FONT = '"Press Start 2P", monospace';
const KIND_COLOR = { daily: "#7bd389", monthly: "#e5986b", goal: "#b28cf0" };

function updateHud(p) {
  document.getElementById("hud-level").textContent = `Lv ${p.level}`;
  document.getElementById("hud-hp").textContent = `${p.hp}/${p.max_hp}`;
  document.getElementById("hp-fill").style.width = `${(100 * p.hp) / p.max_hp}%`;
  const span = p.xp_next_level - p.xp_this_level;
  document.getElementById("hud-xp").textContent = `${p.xp} (next ${p.xp_next_level})`;
  document.getElementById("xp-fill").style.width = `${(100 * (p.xp - p.xp_this_level)) / span}%`;
  document.getElementById("hud-atk").textContent = p.atk;
  document.getElementById("hud-def").textContent = p.defense;
  document.getElementById("hud-items").textContent = p.items.length
    ? `Loot: ${p.items.map((i) => i.name).join(", ")}`
    : "No loot yet";
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
  texture(scene, "door_locked", T, T, (g) => {
    g.fillStyle(0x6b4226).fillRect(0, 0, T, T);
    g.fillStyle(0x4e2f1a).fillRect(7, 0, 2, T).fillRect(15, 0, 2, T).fillRect(23, 0, 2, T);
    g.fillStyle(0xf2c14e).fillRect(12, 15, 8, 8);
    g.lineStyle(2, 0xf2c14e).strokeCircle(16, 13, 3);
  });
  texture(scene, "door_open", T, T, (g) => {
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
    this.spawn = data?.spawn;
  }

  create() {
    if (!this.textures.exists("floor")) makeTextures(this);
    const loading = this.add.text(20, 20, "Loading dungeon...", { fontFamily: FONT, fontSize: "12px" });
    Promise.all([api("/api/rooms"), api("/api/player")])
      .then(([rooms, player]) => {
        updateHud(player);
        this.scene.start("dungeon", { rooms, player, spawn: this.spawn });
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
    this.spawn = data.spawn;
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
    const start = this.spawn ?? { x: 2 * T, y: HALL_ROW * T + T / 2 };
    this.hero.setPosition(start.x, start.y);
    this.physics.add.collider(this.hero, this.walls);

    this.rooms.forEach((room, i) => this.buildRoom(room, i));

    if (this.rooms.length === 0) {
      this.add
        .text(ENTRANCE * T, HALL_ROW * T - 4, "Your dungeon is empty.\nAdd quests on the Quest Board!", {
          fontFamily: FONT, fontSize: "10px", color: "#f2c14e", lineSpacing: 8,
        })
        .setOrigin(0, 0.5);
    }

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

  buildRoom(room, i) {
    const col = Math.floor(i / 2);
    const top = i % 2 === 0;
    const doorX = (ENTRANCE + ROOM_W * col + 3) * T + T / 2;
    const doorY = (top ? 5 : 9) * T + T / 2;
    const centerY = (top ? 3 : 12) * T;

    // The wall tile where the door goes gets replaced by a door.
    this.walls.getChildren()
      .filter((w) => w.x === doorX && w.y === doorY)
      .forEach((w) => w.destroy());
    if (room.unlocked) {
      this.add.image(doorX, doorY, "door_open");
    } else {
      this.walls.create(doorX, doorY, "door_locked");
    }

    const labelY = (top ? 1 : 10) * T + 2;
    this.add
      .text(doorX, labelY, room.title, {
        fontFamily: FONT, fontSize: "8px", color: KIND_COLOR[room.kind], align: "center",
        wordWrap: { width: (ROOM_W - 1) * T - 8 },
      })
      .setOrigin(0.5, 0);

    const enemyKey = `enemy_${room.enemy.tier}`;
    if (room.cleared) {
      this.add.image(doorX, centerY + 8, "chest");
      this.add.text(doorX, centerY + 26, "CLEARED", { fontFamily: FONT, fontSize: "8px", color: "#7bd389" })
        .setOrigin(0.5, 0);
    } else if (room.unlocked) {
      const enemy = this.physics.add.staticImage(doorX, centerY + 8, enemyKey);
      this.tweens.add({ targets: enemy, y: enemy.y - 4, duration: 600, yoyo: true, repeat: -1 });
      this.physics.add.overlap(this.hero, enemy, () => this.startBattle(room, doorX, top));
    } else {
      // Locked: show the monster as a dark silhouette waiting behind the door.
      this.add.image(doorX, centerY + 8, enemyKey).setTint(0x000000).setAlpha(0.6);
    }

    room.door = { x: doorX, y: doorY, top };
  }

  startBattle(room, doorX, top) {
    if (this.inBattle) return;
    this.inBattle = true;
    const spawn = { x: doorX, y: HALL_ROW * T + T / 2 + (top ? -T / 2 : T / 2) };
    this.cameras.main.flash(250, 255, 255, 255);
    this.time.delayedCall(250, () => this.scene.start("battle", { room, player: this.stats, spawn }));
  }

  update() {
    const k = this.keys;
    const speed = 150;
    const vx = (k.LEFT.isDown || k.A.isDown ? -1 : 0) + (k.RIGHT.isDown || k.D.isDown ? 1 : 0);
    const vy = (k.UP.isDown || k.W.isDown ? -1 : 0) + (k.DOWN.isDown || k.S.isDown ? 1 : 0);
    const len = Math.hypot(vx, vy) || 1;
    this.hero.setVelocity((vx / len) * speed, (vy / len) * speed);
    if (vx) this.hero.setFlipX(vx < 0);

    // Show a hint when standing next to a locked door.
    const near = this.rooms.find(
      (r) => r.door && Phaser.Math.Distance.Between(this.hero.x, this.hero.y, r.door.x, r.door.y) < T * 1.6,
    );
    let hint = "";
    if (near && !near.unlocked) hint = `LOCKED: complete "${near.title}" to open`;
    else if (near && !near.cleared) hint = `A ${near.enemy.name} awaits! (+${near.xp} XP)`;
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
    this.spawn = data.spawn;
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

    this.add.rectangle(0, 0, width, height, 0x120d18).setOrigin(0);
    this.add.rectangle(0, height * 0.62, width, height * 0.38, 0x241c31).setOrigin(0);
    this.add.text(width / 2, 24, `${enemy.tier.toUpperCase()}: ${enemy.name}`, {
      fontFamily: FONT, fontSize: "16px", color: KIND_COLOR[this.room.kind],
    }).setOrigin(0.5, 0);
    this.add.text(width / 2, 52, `Quest: ${this.room.title}`, {
      fontFamily: FONT, fontSize: "9px", color: "#9d90b3",
    }).setOrigin(0.5, 0);

    this.heroSprite = this.add.image(width * 0.25, height * 0.45, "hero").setScale(4);
    const enemyScale = { mob: 5, "mini-boss": 4.5, boss: 3.4 }[enemy.tier];
    this.enemySprite = this.add.image(width * 0.72, height * 0.42, `enemy_${enemy.tier}`).setScale(enemyScale);
    this.tweens.add({ targets: this.enemySprite, y: this.enemySprite.y - 8, duration: 700, yoyo: true, repeat: -1 });

    this.heroBar = this.makeBar(width * 0.25, height * 0.62 - 28, this.stats.username);
    this.enemyBar = this.makeBar(width * 0.72, height * 0.62 - 28, enemy.name);
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

    this.say(`A wild ${enemy.name} appears! It hits for about ${enemy.atk}.`);
    this.refreshButtons();
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
  }

  refreshButtons() {
    this.buttons[1].setText(this.powerCooldown ? `2 Power (${this.powerCooldown})` : "2 Power Strike");
    this.buttons[1].setAlpha(this.powerCooldown ? 0.5 : 1);
    this.menu.setVisible(!this.over);
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

  choose(action) {
    if (action === "continue") return this.finish();
    if (action === "flee" && (!this.busy || this.over)) return this.leave();
    if (this.busy || this.over) return;
    if (action === "power" && this.powerCooldown) return this.say("Power Strike is still recharging!");

    this.busy = true;
    if (this.powerCooldown) this.powerCooldown--;
    const roll = () => Phaser.Math.FloatBetween(0.8, 1.2);
    let text;
    if (action === "attack" || action === "power") {
      const crit = Math.random() < 0.12;
      let dmg = Math.round(this.stats.atk * roll() * (action === "power" ? 2.2 : 1) * (crit ? 1.5 : 1));
      if (action === "power") this.powerCooldown = 3;
      this.enemyHp -= dmg;
      this.hitEffect(this.enemySprite);
      this.floatText(this.enemySprite.x, this.enemySprite.y - 60, `-${dmg}`, crit ? "#f2c14e" : "#ffffff");
      text = `${action === "power" ? "POWER STRIKE! " : ""}${crit ? "Critical hit! " : ""}You deal ${dmg} damage.`;
    } else {
      this.defending = true;
      const heal = Math.min(6, this.stats.max_hp - this.heroHp);
      this.heroHp += heal;
      if (heal) this.floatText(this.heroSprite.x, this.heroSprite.y - 70, `+${heal}`, "#7bd389");
      text = `You raise your shield${heal ? ` and recover ${heal} HP` : ""}.`;
    }
    this.say(text);
    this.refreshBars();
    this.refreshButtons();

    if (this.enemyHp <= 0) return this.time.delayedCall(500, () => this.win());
    this.time.delayedCall(700, () => this.enemyTurn());
  }

  enemyTurn() {
    const enemy = this.room.enemy;
    let dmg = Math.max(1, Math.round(enemy.atk * Phaser.Math.FloatBetween(0.8, 1.2)) - this.stats.defense);
    if (this.defending) dmg = Math.ceil(dmg * 0.3);
    this.defending = false;
    this.heroHp -= dmg;
    this.tweens.add({ targets: this.enemySprite, x: this.enemySprite.x - 40, duration: 120, yoyo: true });
    this.hitEffect(this.heroSprite);
    this.cameras.main.shake(150, 0.006);
    this.floatText(this.heroSprite.x, this.heroSprite.y - 70, `-${dmg}`, "#e56b6f");
    this.say(`${enemy.name} attacks for ${dmg} damage!`);
    this.refreshBars();
    if (this.heroHp <= 0) return this.lose();
    this.busy = false;
  }

  async win() {
    this.over = true;
    this.refreshButtons();
    this.tweens.killTweensOf(this.enemySprite);
    this.tweens.add({ targets: this.enemySprite, alpha: 0, scale: 0, angle: 180, duration: 600 });
    this.add.particles(this.enemySprite.x, this.enemySprite.y, "spark", {
      speed: { min: 80, max: 260 }, lifespan: 700, quantity: 40, tint: [0xf2c14e, 0xffffff, 0xe56b6f], emitting: false,
    }).explode(40);
    this.say("Victory! Claiming your reward...");
    try {
      const result = await api(`/api/rooms/${this.room.task_id}/clear`, { method: "POST" });
      updateHud(result.player);
      const loot = result.loot ? `\nLoot: ${result.loot.name} (+${result.loot.atk} ATK, +${result.loot.defense} DEF)` : "";
      const levelUp = result.player.level > this.stats.level ? `\nLEVEL UP! You are now level ${result.player.level}!` : "";
      this.say(`Victory! +${result.xp} XP${levelUp}${loot}\n\nPress SPACE to return.`);
      this.floatText(this.scale.width / 2, this.scale.height * 0.3, `+${result.xp} XP`, "#f2c14e");
    } catch (err) {
      this.say(`Victory... but the reward was refused: ${err.message}\n\nPress SPACE to return.`);
    }
    this.result = "won";
  }

  lose() {
    this.over = true;
    this.result = "lost";
    this.refreshButtons();
    this.tweens.add({ targets: this.heroSprite, alpha: 0.3, angle: -90, duration: 500 });
    this.say("You were defeated... No penalty: rest up and try again.\n\nPress SPACE to retry, ESC to leave.");
  }

  finish() {
    if (!this.over || !this.result) return;
    if (this.result === "lost") return this.scene.restart();
    this.leave();
  }

  leave() {
    this.scene.start("boot", { spawn: this.spawn });
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
