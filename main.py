import os
import random
import uw
import signal


class Bot:
    def __init__(self):
        self.game = uw.Game()
        self.step = 0

        # register update callback
        self.game.add_update_callback(self.update_callback_closure())

    def start(self):
        pid = os.getpid()
        self.game.log_info(f"process ID: {pid}")
        self.game.log_info("starting")
        self.game.set_player_name("bot-py")
        if not self.game.try_reconnect():
            self.game.log_info("Failed to reconnect - will connect to a new game")
            self.game.set_start_gui(True)
            lobby = os.environ.get("UNNATURAL_CONNECT_LOBBY", "")
            addr = os.environ.get("UNNATURAL_CONNECT_ADDR", "")
            port = os.environ.get("UNNATURAL_CONNECT_PORT", "")
            if lobby != "":
                res = self.game.connect_lobby_id(lobby)
            elif addr != "" and port != "":
                res = self.game.connect_direct(addr, port)
            else:
                res = self.game.connect_new_server() # extra_params="-m special/combat-test.uw")
            self.game.log_info(f"Connect result: {res}")

        self.game.log_info("done")
        self.game.log_info("killing self")
        self.game.log_info(f"process ID: {pid}")
        os.kill(pid, signal.SIGTERM)
        
    def attack_nearest_enemies(self):
        own_units = [
            e
            for e in self.game.world.entities().values()
            if e.own()
            and e.has("Unit")
            and self.game.prototypes.unit(e.Proto.proto)
            and self.game.prototypes.unit(e.Proto.proto).get("dps", 0) > 0
        ]
        if not own_units:
            return

        enemy_units = [
            e
            for e in self.game.world.entities().values()
            if e.policy() == uw.Policy.Enemy and e.has("Unit")
        ]
        if not enemy_units:
            return

        for u in own_units:
            _id = u.Id
            pos = u.Position.position
            if len(self.game.commands.orders(_id)) == 0:
                enemy = sorted(
                    enemy_units,
                    key=lambda x: self.game.map.distance_estimate(
                        pos, x.Position.position
                    ),
                )[0]
                self.game.commands.order(
                    _id, self.game.commands.fight_to_entity(enemy.Id)
                )

    def assign_random_recipes(self):
        for e in self.game.world.entities().values():
            if not (e.own() and hasattr(e, "Unit")):
                continue
            recipes = self.game.prototypes.unit(e.Proto.proto)
            if not recipes:
                continue
            recipes = recipes["recipes"]
            if len(recipes) > 0:
                self.game.commands.command_set_recipe(e.Id, random.choice(recipes))

    def update_callback_closure(self):
        def update_callback(stepping):
            if not stepping:
                return
            self.step += 1  # save some cpu cycles by splitting work over multiple steps

            if self.step % 10 == 1:
                self.attack_nearest_enemies()

            if self.step % 10 == 5:
                self.assign_random_recipes()

        return update_callback


if __name__ == "__main__":
    bot = Bot()
    bot.start()
