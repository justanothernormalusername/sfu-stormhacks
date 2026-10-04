// Exercise the actual scene transitions without requiring a browser or CDN.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const context = vm.createContext({
  Phaser: { Scene: class {} },
  document: { fonts: { load: () => ({ finally() {} }) } },
});
vm.runInContext(fs.readFileSync("src/app/static/game/main.js", "utf8") +
  "\nglobalThis.scenes = { BootScene, DungeonScene, BattleScene };", context);
const { BootScene, DungeonScene, BattleScene } = context.scenes;
const dungeon = new DungeonScene();
dungeon.rooms = Array.from({ length: 12 }, (_, index) => ({ index }));
const grid = dungeon.buildGrid();
const centers = dungeon.rooms.map((room) => dungeon.roomCenter(room.index));
assert.equal(new Set(centers.map((center) => center.y)).size, 1, "rooms must form one line");
for (let i = 1; i < dungeon.rooms.length; i++) {
  const point = dungeon.walkwayPoint(i);
  assert.equal(grid[Math.floor(point.y / 32)][Math.floor(point.x / 32)], "h");
  assert.ok(centers[i].x > centers[i - 1].x);
}
assert.equal(dungeon.exitLocked({ safe: false, cleared: false }, 1), true);
assert.equal(dungeon.exitLocked({ safe: false, cleared: true }, 1), false);
assert.equal(dungeon.exitLocked({ safe: true, cleared: false }, 1), false);
assert.equal(dungeon.exitLocked({ safe: false, cleared: false }, 11), false);
for (const room of dungeon.rooms.slice(1)) {
  room.center = dungeon.roomCenter(room.index);
  dungeon.inBattle = false;
  dungeon.stats = {};
  dungeon.cameras = { main: { flash() {} } };
  dungeon.time = { delayedCall: (_, callback) => callback() };
  dungeon.scene = { start(name, data) {
    assert.equal(name, "battle");
    const battle = new BattleScene();
    battle.init(data);
    battle.over = true;
    battle.settling = false;
    battle.scene = { start(scene, spawn) {
      assert.equal(scene, "boot");
      if (battle.result === "lost") {
        assert.equal(Object.keys(spawn).length, 0);
      } else if (battle.result === "won") {
        assert.equal(spawn.spawnRoom, room.index);
      } else {
        assert.equal(spawn.spawnRoom, undefined);
        assert.equal(spawn.spawnPoint.x, dungeon.walkwayPoint(room.index).x);
        assert.equal(grid[Math.floor(spawn.spawnPoint.y / 32)][Math.floor(spawn.spawnPoint.x / 32)], "h");
        for (const enemyRoom of dungeon.rooms) {
          const enemy = dungeon.roomCenter(enemyRoom.index);
          assert.ok(Math.hypot(spawn.spawnPoint.x - enemy.x, spawn.spawnPoint.y - enemy.y) > 80);
        }
      }
      const boot = new BootScene();
      boot.init({ spawnRoom: 10 });
      boot.init(spawn);
      assert.equal(boot.spawnRoom, spawn.spawnRoom);
    } };
    for (const result of ["fled", "error", "lost", "won"]) {
      battle.result = result;
      battle.finish();
    }
  } };
  dungeon.startBattle(room);
}
console.log("Spawn checks passed for fleeing, errors, death, and victory in every room.");

// Reuse the same scene, as Phaser does. Escape must return immediately after
// the server closes the fight, without a second keypress or stale result state.
(async () => {
  const battle = new BattleScene();
  let requests = 0;
  let returns = 0;
  context.api = async (path, options) => {
    requests++;
    assert.equal(path, "/api/rooms/1/act");
    assert.equal(options.body.action, "flee");
    return { fight: { state: "fled" } };
  };
  battle.applyFight = (result) => { battle.fight = result.fight; battle.busy = false; };
  battle.scene = { start(scene, data) {
    returns++;
    assert.equal(scene, "boot");
    assert.equal(data.spawnPoint.x, 240);
    assert.equal(data.spawnPoint.y, 240);
    assert.equal(data.spawnRoom, undefined);
  } };
  for (let attempt = 0; attempt < 3; attempt++) {
    battle.init({ room: { index: 1 }, player: {}, retreatPoint: { x: 240, y: 240 } });
    assert.equal(battle.result, null);
    assert.equal(battle.fight, null);
    assert.equal(battle.over, false);
    await battle.choose("flee");
    assert.equal(requests, attempt + 1);
    assert.equal(returns, attempt + 1);
  }
  console.log("Repeated flee actions return immediately without pressing Space.");
})().catch((error) => { console.error(error); process.exitCode = 1; });
