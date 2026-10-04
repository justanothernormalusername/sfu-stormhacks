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
const grid = dungeon.buildGrid(41, 6);
for (const room of dungeon.rooms) {
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
        assert.equal(spawn.spawnPoint.x, room.center.x);
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
