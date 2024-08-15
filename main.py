import os
import random
import uw
import signal
import json
from collections import defaultdict
import traceback

SOURCES = [
    "metal"
]

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            # Try the default serialization method
            return super().default(obj)
        except TypeError:
            # If serialization fails, iterate over the object's dict representation and convert each value
            # if there are no dict representation, return the string representation of the object
            try:
                return {k: v for k, v in obj.__dict__.items()}
            except AttributeError:
                return str(obj)

def to_json(obj):
    return json.dumps(obj, cls=CustomJSONEncoder, indent=4)

class Bot:
    def __init__(self):
        self.game = uw.Game()
        self.step = 0
        self.prototypes = []
        self.construction_ids = {}
        self.main_building = None
        self.resources_map = defaultdict(list)
        self.drill_positions = defaultdict(list)
        self.talos_positions = defaultdict(list) 
        self.buildings = defaultdict(list)

        # register update callback
        self.game.add_update_callback(self.update_callback_closure())

    def start(self):
        pid = os.getpid()
        self.game.log_info(f"process ID: {pid}")
        self.game.log_info("starting")
        self.game.set_player_name("Simon")

        if False:
            self.game.set_start_gui(True)
            self.game.connect_direct("192.168.2.102", 27543)
            os.kill(pid, signal.SIGTERM)

        if not self.game.try_reconnect():
            self.game.set_start_gui(True)
            # self.game.connect_new_server(extra_params="-m special/combat-test.uw")
            self.game.connect_new_server(extra_params="-m planets/triangularprism.uw") # --allowUwApiAdmin 1")

        self.game.log_info("done - killing self")
        self.game.log_info(f"process ID: {pid}")
        os.kill(pid, signal.SIGTERM)

    def entity_to_json(self, e, print_distance=True):
        _id = e.Id
        pos = e.Position.position
        
        info = {
            "id": _id,
            "pos": pos,
            "unit": self.game.prototypes.unit(e.Proto.proto),
            "resource": self.game.prototypes.resource(e.Proto.proto),
            "construction": self.game.prototypes.construction(e.Proto.proto)
        }
        info = dict(filter(lambda x: x[1], info.items()))

        if print_distance:
            dist = self.game.map.distance_estimate(self.main_building.Position.position, pos)
            info["distance_to_main_building"] = dist

        print(json.dumps(info, indent=4), flush=True)
    
    def unit(self, entity):
        self.game.prototypes.unit(entity.Proto.proto)

    def is_atv(self, entity):
        return entity.has("Unit") and entity.name() == "ATV"
        
    def init_prototypes(self):
        if self.prototypes:
            return
        for p in self.game.prototypes.all():
            name = str(self.game.prototypes.name(p))
            type = str(self.game.prototypes.type(p))
            self.prototypes.append({
                "id": p,
                "name": name,
                "type": type,
                "json": self.game.prototypes.json(p),
            })
            if type == "Prototype.Construction":
                print(f"Construction: {name}")
                self.construction_ids[name] = p


    def get_closest_ores(self):
        if self.resources_map:
            return
        for e in self.game.world.entities().values():
            if not (hasattr(e, "Unit")) and not e.own():
                continue
            unit = self.game.prototypes.unit(e.Proto.proto)
            if not unit:
                continue
            if "deposit" not in unit.get("name", ""):
                continue
            name = unit.get("name", "").replace(" deposit", "")
            self.resources_map[name].append(e)
        if not self.main_building:
            return
        for r in self.resources_map:
            self.resources_map[r].sort(key=lambda x: self.game.map.distance_estimate(
                        self.main_building.Position.position, x.Position.position
                    ))

    def find_main_base(self):
        if self.main_building:
            return
        for e in self.game.world.entities().values():
            if not (e.own() and hasattr(e, "Unit")):
                continue
            unit = self.game.prototypes.unit(e.Proto.proto)
            if not unit:
                continue
            if unit.get("name", "") == "nucleus":
                self.main_building = e

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

    def assign_recipes(self):
        for e in self.game.world.entities().values():
            if not (e.own() and hasattr(e, "Unit")):
                continue
            recipes = self.game.prototypes.unit(e.Proto.proto)
            if not recipes:
                continue
            recipes = recipes["recipes"]
            if len(recipes) > 0:
                recipe = None
                for r in recipes:
                    # plasma blaster, shield priojector, jaggernaut
                    if r in [2688628973, 4128605704, 3556640323]:
                        self.game.commands.command_set_recipe(e.Id, r)
    
    def build(self, construction, position):
        print(f"Building {construction} at {position}")
        construction_id = self.construction_ids.get(construction)
        self.game.commands.command_place_construction(construction_id, position)
        self.buildings[construction].append(int(position))
        print(f"buildings[{construction}]: {self.buildings[construction]}")

    def build_nearby(self, construction, position):
        construction_id = self.construction_ids.get(construction)
        pos = self.game.map.find_construction_placement(construction_id, position)
        self.build(self, construction, pos)
        return pos

    def build_nearby_drill(self, construction, resource, index=0):
        drills = self.drill_positions.get(resource, [self.main_building.Position.position])
        print(f"Building {construction} near {resource}")
        print(f"drills: {drills}")
        construction_id = self.construction_ids.get(construction)
        pos = self.game.map.find_construction_placement(construction_id, drills[index])
        self.build(construction, pos)
        return pos

    def build_nearby_building(self, construction, building, index=0):
        buildings = self.buildings.get(building, [self.main_building.Position.position])
        print(f"Building {construction} near {building}")
        print(f"buildings: {buildings}")
        construction_id = self.construction_ids.get(construction)
        pos = self.game.map.find_construction_placement(construction_id, buildings[index])
        self.build(construction, pos)
        return pos

    def build_drills(self, resource, count):
        if resource in ["metal", "crystals"]:
            # drill
            print("Building drill")
            construction_id = 3148228606
        else:
            # pump
            print("Building pump")
            construction_id = 2775974627

        deposits = self.resources_map.get(resource, [])
        print(f"Building {count} {resource} drills")
        print(f"Main building: {self.main_building.Position.position}")
        print(f"Found {resource} deposits: {len(deposits)}")
        for e in deposits[:count]:
            self.entity_to_json(e)
            self.game.commands.command_place_construction(construction_id, e.Position.position)
            print(f"Building drill at {e.Position.position}")
            self.drill_positions[resource].append(e.Position.position)
            # self.build_nearby(construction_id, e.Position.position)


    def build_arsenal(self):
        # pos = self.drill_positions.get("metal", [])[1]
        self.build_nearby_drill("arsenal", "metal", 1)

    def build_laboratory(self):
        self.build_nearby_drill("laboratory", "crystals")
    
    def build_bot_assembler(self):
        self.build_nearby_building("bot assembler", "laboratory")

    def build_concrete_plant(self):
        if not self.buildings.get("concrete plant"):
            self.build_nearby_drill("concrete plant", "metal")
            return
        
        self.build_nearby_building("concrete plant", "concrete plant")
        

    def build_talos(self):
        talos_construction_id = self.construction_ids.get("talos")
        if len(self.talos_positions) == 0:
            for resource in self.drill_positions.keys():
                for pos in self.drill_positions[resource]:
                    self.build_nearby(talos_construction_id, pos)
                    self.talos_positions.append([pos])
            return
        
        for x, pos in enumerate(self.talos_positions[-1]):
            self.build_nearby(talos_construction_id, pos)
            self.talos_positions.append(pos)
    
    def destroy_concrete_plant(self):
        for e in self.game.world.entities().values():
            if not e.own():
                continue
            if not e.has("Unit"):
                continue
            unit = self.game.prototypes.unit(e.Proto.proto)
            if not unit:
                continue
            if unit.get("name", "") == "concrete plant":
                self.game.commands.command_self_destruct(e.Id)
                return

    def enable_buildings(self):
        # iterate all own buildings
        for e in self.game.world.entities().values():
            if not e.own():
                continue
            if not e.has("Construction"):
                continue
            if e.has("Disabled"):
                self.game.commands.command_set_priority(e.Id, 1)

    def update_callback_closure(self):
        def update_callback(stepping):
            if not stepping:
                return
            self.step += 1  # save some cpu cycles by splitting work over multiple steps

            try:
                if self.step < 10:
                    self.init_prototypes()
                    self.find_main_base()
                    self.get_closest_ores()
                
                # if self.step == 12:
                #     self.step += 850
                
                if self.step == 2:
                    self.build_drills("metal", 3)

                if self.step == 240:
                    self.build_concrete_plant()

                if self.step == 290:
                    self.build_concrete_plant()

                if self.step == 451:
                    self.build_drills("crystals", 1)
                
                if self.step == 551:
                    self.build_drills("oil", 1)

                if self.step == 801:
                    self.build_laboratory()

                if self.step == 901:
                    self.build_arsenal()
                
                if self.step == 1101:
                    self.build_nearby_building("bot assembler", "laboratory")

                # 1600 built factory

                if self.step == 2000:
                    self.destroy_concrete_plant()

                if self.step == 3000 and self.step % 3000 == 0:
                    self.build_nearby("bot assembler", self.main_building.Position.position)

                if self.step > 20000 and self.step % 10 == 2:
                    self.attack_nearest_enemies()

                if self.step % 10 == 3:
                    self.assign_recipes()
                    self.enable_buildings()

                if self.step % 100 == 0:
                    self.game.log_info(f"step: {self.step}")

            except Exception as e:
                print(f"Error: {e}\n", flush=True)
                # print exception stack trace
                traceback.print_exc()



        return update_callback
    
    def write_prototypes(self):
        with open("prototypes.json", "w") as f:
            f.write(json.dumps(self.prototypes, indent=4))
            print("Prototypes written to file")


if __name__ == "__main__":
    bot = Bot()
    bot.start()
