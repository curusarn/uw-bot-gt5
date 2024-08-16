import os
import random
import uw
import signal
import json
from collections import defaultdict
import traceback
import time

class Bot:
    def __init__(self):
        self.game = uw.Game()
        self.step = 0
        self.prototypes = {} 
        self.construction_ids = {}
        self.construction_names = {}
        self.recipe_id_by_name = {}
        self.main_building = None
        self.resources_map = defaultdict(list)
        self.drill_positions = defaultdict(list)
        self.talos_positions = defaultdict(list) 
        self.building_positions = defaultdict(list)

        self.resource_counts = defaultdict(int)
        self.constructions = defaultdict(list)
        self.buildings = defaultdict(list)

        self.initialized = False

        # register update callback
        self.game.add_update_callback(self.update_callback_closure())

    def start(self):
        pid = os.getpid()
        self.game.log_info(f"process ID: {pid}")
        self.game.log_info("starting")
        self.game.set_player_name("Simon")
        # set color red
        self.game.set_player_color(1, 0, 0)

        if not self.game.try_reconnect():
            port = None 
            if port:
                self.game.set_start_gui(True)
                self.game.connect_direct("192.168.2.102", port)
                os.kill(pid, signal.SIGTERM)
                return

            self.game.set_start_gui(True)
            # self.game.connect_new_server(extra_params="-m special/combat-test.uw")
            maps = ["planets/triangularprism.uw", "planets/h3o.uw", "planets/hexagon.uw", "planets/torus.uw", "planets/box.uw", "planets/octahedron.uw"]
            random_map = random.choice(maps)
            self.game.connect_new_server(extra_params=f"-m {random_map}") # --allowUwApiAdmin 1")
            #self.game.connect_new_server(extra_params="-m planets/triangularprism.uw") # --allowUwApiAdmin 1")

        os.kill(pid, signal.SIGTERM)

    def entity_to_json(self, e, distance=False, show_recipe=False, show_prototype=False):
        _id = e.Id
        pos = e.Position.position
        
        recipe = None
        if show_recipe and e.has("Recipe"):
            recipe = self.game.prototypes.recipes(e.Recipe.recipe)
        
        is_construction = e.Proto.proto in self.construction_names

        prototype = self.prototypes.get(e.Proto.proto, None)
        type = prototype.get("type", "") if prototype else None

        if not show_prototype:
            prototype = None

        info = {
            "id": _id,
            "type": type,
            "pos": pos,
            "unit": self.game.prototypes.unit(e.Proto.proto),
            "resource": self.game.prototypes.resource(e.Proto.proto),
            "construction": self.game.prototypes.construction(e.Proto.proto),
            "recipe": recipe,
            "is_construction": is_construction,
            "prototype": prototype,
        }
        info = dict(filter(lambda x: x[1] is not None, info.items()))

        if distance:
            dist = self.game.map.distance_estimate(self.main_building.Position.position, pos)
            info["distance_to_main_building"] = dist

        return json.dumps(info, indent=4)

    def print_entity(self, e, print_distance=True):
        print(self.entity_to_json(e, print_distance))
    
    def unit(self, entity):
        self.game.prototypes.unit(entity.Proto.proto)

    def is_atv(self, entity):
        return entity.has("Unit") and entity.name() == "ATV"
        
    def init_prototypes(self):
        if len(self.prototypes) > 0:
            return
        for p in self.game.prototypes.all():
            name = str(self.game.prototypes.name(p))
            type = str(self.game.prototypes.type(p))
            self.prototypes[p] = {
                "id": p,
                "name": name,
                "type": type,
                "json": self.game.prototypes.json(p),
            }
            if type == "Prototype.Construction":
                print(f"Adding construction prototype: {name}")
                self.construction_ids[name] = p
                self.construction_names[p] = name
            elif type == "Prototype.Recipe":
                self.recipe_id_by_name[name] = p

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

    def attack(self, aggression=False, closest_to_self=False):
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
            { "e": e, "dist": self.game.map.distance_estimate(e.Position.position, self.main_building.Position.position) }
            for e in self.game.world.entities().values()
            if e.policy() == uw.Policy.Enemy and e.has("Unit") and self.game.prototypes.unit(e.Proto.proto).get("name", "") != "eagle"
        ]
        threshold = 20000 if aggression else 710
        enemy_units = sorted(filter(lambda x: x["dist"] < threshold, enemy_units), key=lambda x: x["dist"])
        if not enemy_units:
            print("No enemy units found - falling back to nucleus")
            if random.random() > 0.80:
                self.scatter()
            else:
                self.send_to_nucleus()
            return

        print(f"Attacking closest enemy unit, distance {enemy_units[0]['dist']}")
        for u in own_units:
            _id = u.Id
            pos = u.Position.position
            if len(self.game.commands.orders(_id)) > 0:
               continue
            
            if closest_to_self:
                enemy_units = sorted(enemy_units, key=lambda x: self.game.map.distance_estimate(x["e"].Position.position, pos))

            self.game.commands.order(
                _id, self.game.commands.fight_to_entity(enemy_units[0]["e"].Id)
            )
    

    def attack_nearest_enemies(self, clear_orders=True, entity=None):
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
            if len(self.game.commands.orders(_id)) == 0 or clear_orders:
                enemy = sorted(
                    enemy_units,
                    key=lambda x: self.game.map.distance_estimate(
                        pos, x.Position.position
                    ),
                )[0]
                if entity is not None:
                    enemy = entity
                self.game.commands.order(
                    _id, self.game.commands.fight_to_entity(enemy.Id)
                )
    
    def scatter(self):
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

        for u in own_units:
            _id = u.Id
            pos = u.Position.position
            neighbors = self.game.map.neighbors_of_position(pos)
            new_pos = random.choice(neighbors)
            self.game.commands.order(
                _id, self.game.commands.run_to_position(new_pos)
            )
    


    def assign_recipes(self):
        for e in self.game.world.entities().values():
            if not (e.own() and hasattr(e, "Unit")):
                continue
            unit = self.game.prototypes.unit(e.Proto.proto)
            if not unit:
                continue
            name = unit.get("name", "")
            recipes = unit["recipes"]
            if len(recipes) > 0:
                if name == "laboratory":
                    if self.is_nearby(e, "crystals deposit", radius=15):
                        self.game.commands.command_set_recipe(e.Id, self.recipe_id_by_name.get("shield projector"))
                    elif self.is_nearby(e, "generator", radius=2):
                        self.game.commands.command_set_recipe(e.Id, self.recipe_id_by_name.get("quantum ray"))
                    else:
                        # smelter
                        self.game.commands.command_set_recipe(e.Id, self.recipe_id_by_name.get("atomic forge"))
                elif name == "forgepress":
                    if self.is_nearby(e, "metal deposit", radius=15):
                        self.game.commands.command_set_recipe(e.Id, self.recipe_id_by_name.get("armor plates"))
                    else:
                        # smelter
                        self.game.commands.command_set_recipe(e.Id, self.recipe_id_by_name.get("reinforced plates"))
                elif name == "experimental assembler":
                    self.game.commands.command_set_recipe(e.Id, self.recipe_id_by_name.get("colossus"))
                else:
                    recipe = None
                    for r in recipes:
                        # plasma blaster, shield priojector, jaggernaut, atv
                        if r in [2688628973, 4128605704, 3556640323, 2717031940]:
                            self.game.commands.command_set_recipe(e.Id, r)
    
    def is_nearby(self, entity, name, radius=1):
        # neighbours = self.game.map.neighbors_of_position(entity.Position.position)
        total_radius = self.game.prototypes.unit(entity.Proto.proto).get("buildingRadius", 0) + radius
        positions = self.game.map.area_neighborhood(entity.Position.position, total_radius)

        for pos in positions:
            entities = self.game.map.entities(pos)
            for e_ in entities:
                e = self.game.world.entities().get(e_)
                if e.has("Unit") and self.game.prototypes.unit(e.Proto.proto).get("name", "") == name:
                    return True
        
        return False


    def get_recipe(self, name):
        self.game.recipes.get(name)

    def get_own_buildings(self):
        self.atvs = []
        self.juggernauts = []
        self.colossus = []
        self.buildings = defaultdict(list)
        self.drill_positions = defaultdict(list)
        self.building_positions = defaultdict(list)
        self.resource_counts = defaultdict(int)
        self.constructions = defaultdict(list) 
        self.enemy_main_buildings = []

        for e in self.game.world.entities().values():
            
            if not e.has("Proto"):
                continue
            
            prototype = self.prototypes.get(e.Proto.proto, {})
            type = prototype.get("type", "")
            name = prototype.get("name", "")

            if name == "nucleus" and not e.own():
                self.enemy_main_buildings.append(e)  

            if not e.own():
                continue

            if type == "Prototype.Construction":
                self.constructions[name].append(e)
                print(f"Enabling {name}")
                # recipes = self.game.prototypes.unit(prototype.id).get("recipes", [])
                # for r in recipes:
                #     if r in [2688628973, 4128605704, 3556640323, 2717031940]:
                #         self.game.commands.command_set_recipe(e.Id, r)

                self.game.commands.command_set_priority(e.Id, 1)
                continue

            if type == "Prototype.Resource":
                self.resource_counts[name] += e.Amount.amount
                continue

            if name == "ATV":
                self.atvs.append(e)
                continue

            if name == "juggernaut":
                self.juggernauts.append(e)
                continue
            
            if name == "colossus":
                self.colossus.append(e)
                continue

            props = self.game.prototypes.json(e.Proto.proto)

            if props.get("buildingRadius", 0) > 0:
                self.buildings[name].append(e)
                self.building_positions[name].append(int(e.Position.position))

                # print(f"Building: {self.entity_to_json(e)}")
                if name == "nucleus":
                    self.main_building = e
                elif name in ["drill", "pump"]:
                    # get recipe
                    recipe_id = e.Recipe.recipe
                    recipe = self.game.prototypes.recipes(recipe_id)
                    self.drill_positions[recipe["name"]].append(int(e.Position.position))
                continue

            self.print_entity(e)

    def build(self, construction, position):
        print(f"Building {construction} at {position} @ step {self.step}")
        construction_id = self.construction_ids.get(construction)
        if position is None:
            print(f"ERROR: No position passed for {construction} - using nucleuas position")
            position = self.main_building.Position.position
            position = self.game.map.find_construction_placement(construction_id, position)

        self.game.commands.command_place_construction(construction_id, position)
        self.building_positions[construction].append(int(position))
        print(f"buildings[{construction}]: {self.buildings[construction]}")

    def build_nearby(self, construction, position, with_gap=False):
        construction_id = None
        if with_gap:
            construction_id = self.construction_ids.get("experimental assembler")
        else:
            construction_id = self.construction_ids.get(construction)

        if construction_id is None:
            print(f"ERROR: No construction_id found for {construction}")
            return

        pos = self.game.map.find_construction_placement(construction_id, position)
        self.build(construction, pos)
        return pos

    def build_nearby_drill(self, construction, resource, index=0, with_gap=False):
        drills = self.drill_positions.get(resource, [])
        deposits = self.resources_map.get(resource, [])
        drills += list(map(lambda x: x.Position.position, deposits))
        drills += [self.main_building.Position.position] * (index + 2)
        
        print(f"Building {construction} near {resource}")
        construction_id = None
        if with_gap:
            construction_id = self.construction_ids.get("experimental assembler")
        else:
            construction_id = self.construction_ids.get(construction)

        print(f"construction_id: {construction_id} for '{construction}'")
        pos = self.game.map.find_construction_placement(construction_id, drills[index])
        self.build(construction, pos)
        return pos

    def build_nearby_building(self, construction, building, index=0, with_gap=False):
        buildings = self.buildings.get(building, [])

        if not buildings or len(buildings) == 0:
            print(f"No buildings found for {building}")
            buildings = self.constructions.get(building, [self.main_building] * (index + 2))

        building_positions = list(map(lambda x: x.Position.position, buildings))

        print(f"Building {construction} near {building}")
        print(f"buildings: {buildings}")

        construction_id = None
        if with_gap:
            construction_id = self.construction_ids.get("experimental assembler")
        else:
            construction_id = self.construction_ids.get(construction)

        pos = self.game.map.find_construction_placement(construction_id, building_positions[index])
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
        # print(f"Found {resource} deposits: {len(deposits)}")
        for e in deposits[:count]:
            # self.print_entity(e)
            self.game.commands.command_place_construction(construction_id, e.Position.position)
            print(f"Building drill at {e.Position.position}")
            self.drill_positions[resource].append(int(e.Position.position))
    
    def print_stats(self):
        print(f"\n\n========= STATS @ step {self.step} =========")
        print(f"Main building: {self.main_building.Position.position}")
        print(f"ATVs: {len(self.atvs)}")
        print(f"Juggernauts: {len(self.juggernauts)}")
        print(f"Drills:")
        for resource in self.drill_positions.keys():
            print(f"  {resource}: {len(self.drill_positions[resource])}")
        print(f"Buildings:")
        for building in self.buildings.keys():
            print(f"  {building}: {len(self.buildings[building])}")
        print(f"Constructions:")
        for building in self.constructions.keys():
            print(f"  {building}: {len(self.constructions[building])}")
        print(f"Resources:")
        for resource in self.resource_counts.keys():
            print(f"  {resource}: {self.resource_counts[resource]}")

    def build_talos(self, with_gap=False, distance=260):
        enemies = [
            e
            for e in self.game.world.entities().values()
            if e.policy() == uw.Policy.Enemy
            and e.has("Unit")
            # and self.game.prototypes.unit(e.Proto.proto).get("name", "") != "eagle"
        ]
        closest_enemy = None
        min_dist = 1000000
        for e in enemies:
            dist = self.game.map.distance_estimate(e.Position.position, self.main_building.Position.position)
            if dist < min_dist:
                min_dist = dist
                closest_enemy = e
        
        if min_dist < 1200:
           return self.build_talos2(distance=distance)

        talos_count = len(self.buildings["talos"])
        # set random threshold to asymtoticly approach 1 as talos_count increases 
        random_threshold = 0.99 - 0.99 * (1 / (talos_count + 1))
        print(f"Talos building random threshold: {random_threshold}")

        if random_threshold > 0.6 and random.random() > 0.9:
            return self.build_talos2(distance=distance)

        positions = self.game.map.area_neighborhood(self.main_building.Position.position, distance)
        taloses = self.buildings.get("talos", []) + self.constructions.get("talos", [])

        bwst_pos = random.choice(positions)
        max_dist = 0
        for pos in positions:
            closest_talos = random.choice(taloses)
            min_dist = 1000000
            for t in taloses:
                tpos = t.Position.position
                dist = self.game.map.distance_estimate(pos, tpos)
                if dist < min_dist:
                    min_dist = dist
                    closest_talos = pos
            
            if min_dist > max_dist and random.random() > random_threshold:
                max_dist = min_dist
                bwst_pos = closest_talos

        self.build_nearby("talos", bwst_pos, with_gap=with_gap)
        return

    def attack_nearest_base(self):
        bases = [{
            "dist": self.game.map.distance_estimate(e.Position.position, self.main_building.Position.position),
            "e": e
        } for e in self.game.world.entities().values() 
            if e.policy() == uw.Policy.Enemy
            and e.has("Unit")
            #and e.game.prototypes.unit(e.Proto.proto).get("name", "") == "nucleus"
            ]

        sorted_bases = sorted(bases, key=lambda x: x["dist"])
        x = 40
        if x > len(sorted_bases):
            x = len(sorted_bases) - 1
        second_closest = sorted_bases[x]["e"]

        self.attack_nearest_enemies(entity=second_closest)


    def build_talos2(self, distance=270):
        positions = self.game.map.area_neighborhood(self.main_building.Position.position, distance)
        dist = 1000000
        nearest_enemy = None
        for e in self.game.world.entities().values():
            if e.policy() != uw.Policy.Enemy:
                continue

            d = self.game.map.distance_estimate(e.Position.position, self.main_building.Position.position)
            if d < dist:
                dist = d
                nearest_enemy = e
                continue
        
        if nearest_enemy:
            closest_position = None
            dist = 1000000
            for pos in positions:
                d = self.game.map.distance_estimate(pos, nearest_enemy.Position.position) 
                if d < dist and d > 120 and random.random() > 0.80:
                    dist = d
                    closest_position = pos

        self.build_nearby("talos", closest_position, with_gap=True)
    
    def destroy_building(self, name):
        print(f"Destroying {name}")
        building = None
        for e in self.game.world.entities().values():
            if not e.own():
                continue
            if not e.has("Unit"):
                continue
            unit = self.game.prototypes.unit(e.Proto.proto)
            if not unit:
                continue
            if unit.get("name", "") == name:
                building = e
                self.game.commands.command_self_destruct(building.Id)
                self.buildings[name] = list(filter(lambda x: x.Id != building.Id, self.buildings[name]))
                return
        
        if building is None:
            print(f"Building {name} not found")
            return
    
    def destroy_temporary_laboratory(self):
        name = "laboratory"
        for e in self.game.world.entities().values():
            if not e.own():
                continue
            # if not e.has("Unit"):
            #     continue
            unit = self.game.prototypes.unit(e.Proto.proto)
            if not unit:
                continue
            if unit.get("name", "") == name:
                print(f"Found {name} at {e.Position.position}")
                if not self.is_nearby(e, "crystals deposit", radius=2) and not self.is_nearby(e, "generator", radius=2):
                    print(f"Destroying {name} - near crystals deposit: {self.is_nearby(e, 'crystals deposit', radius=2)}, near generator: {self.is_nearby(e, 'generator', radius=2)}")
                    self.game.commands.command_self_destruct(e.Id)
                    self.buildings[name] = list(filter(lambda x: x.Id != e.Id, self.buildings[name]))
                    break
        


    def enable_constructions(self):
        # iterate all own buildings
        for name, items in self.constructions.items():
            for e in items:
                print(f"Enabling {name} at {e.Position.position}")
                self.game.commands.command_set_priority(e.Id, 1)

    def have_building(self, name, count):
        return len(self.buildings.get(name, [])) >= count
    
    def have_drill(self, resource, count):
        return len(self.drill_positions.get(resource, [])) >= count
    
    def have_construction(self, name, count):
        return len(self.constructions.get(name, [])) >= count
    
    def have_building_or_construction(self, name, count):
        return (len(self.buildings.get(name, [])) + len(self.constructions.get(name, []))) >= count
    
    def should_build_building(self, name, count):
        return not self.have_building_or_construction(name, count)

    def have_jaggernaut(self, count):
        return len(self.juggernauts) >= count
    
    def have_colossus(self, count):
        return len(self.colossus) >= count

    def have_resources(self, resource, count):
        return self.resource_counts.get(resource, 0) >= count

    def rebuild(self, name):
        self.build_nearby_building(name, name, with_gap=True)
        self.destroy_building(name)
    
    def send_to_nucleus(self):
        own_units = [
            e
            for e in self.game.world.entities().values()
            if e.own() and e.has("Unit")
            and self.game.prototypes.unit(e.Proto.proto).get("dps", 0) > 0
        ]
        print(f"Sending {len(own_units)} units to nucleus")

        if not own_units:
            return

        for u in own_units:
            _id = u.Id
            if len(self.game.commands.orders(_id)) == 0:
                self.game.commands.order(_id, self.game.commands.run_to_entity(self.main_building.Id))

    def update_callback_closure(self):
        def update_callback(stepping):
            if not stepping:
                return
            self.step += 1  # save some cpu cycles by splitting work over multiple steps

            try:
                if self.step == 1:
                    self.init_prototypes()
                    self.find_main_base()
                    self.get_own_buildings()
                    self.get_closest_ores()

                    self.initialized = True                
                    self.step = 2

                if not self.initialized:
                    return

                if self.step % 100 == 0:
                    self.game.log_info(f"step: {self.step}")
                
                if self.step % 10 == 3:
                    self.get_own_buildings()
                    self.assign_recipes()
                    # self.enable_constructions()

                if self.step % 15 == 0:
                    if random.random() > 0.95 or (self.step > 3 and self.step < 57):
                        self.scatter()
                    else:
                        # self.scatter()
                        aggression = self.have_jaggernaut(12) or self.have_colossus(3)
                        # self.send_to_nucleus()
                        # self.attack_nearest_base()
                        self.attack(aggression=aggression, closest_to_self=True)
                        # self.attack_nearest_enemies(clear_orders=True)

                # if self.step % 25 == 4:
                #     self.send_to_nucleus()

                if self.step == 13:
                    self.build_drills("metal", 3)

                # if self.step < 35:
                #     self.destroy_building("talos")

                if self.step == 29:
                    print("Manual")
                    #self.scatter()
                    # self.send_to_nucleus()
                    self.rebuild("concrete plant")
                    # self.destroy_building("laboratory")
                    # self.build_nearby_building("smelter", "smelter")
                    # self.build_nearby_building("arsenal", "arsenal")

                    
                if self.step % 50 == 0:                
                    self.get_own_buildings()
                    self.print_stats()
                    return

                if self.step % 40 == 11:
                    if self.have_jaggernaut(1) and self.have_resources("metal", 6) and self.have_resources("reinforced concrete", 6) and not self.have_construction("talos", 2):
                        self.build_talos()
                        # self.build_talos2()
                        return

                    # build

                    c_strat = True

                    if self.have_drill("metal", 1) and self.should_build_building("concrete plant", 1):
                        self.build_nearby_drill("concrete plant", "metal", 0)
                        return
                    
                    if not self.have_building("bot assembler", 1) and self.have_building_or_construction("concrete plant", 1) and self.should_build_building("concrete plant", 2):
                        self.build_nearby_building("concrete plant", "concerte plant")
                        return

                    if self.have_building("concrete plant", 2) and self.have_building("drill", 2) and self.should_build_building("drill", 4):
                        self.build_drills("crystals", 1)
                        return

                    if not self.have_building("drill", 4) and self.should_build_building("talos", 1):
                        self.build_nearby_drill("talos", "crystals", 0, with_gap=True)
                        return
                
                    if (self.have_building_or_construction("drill", 4)) and self.should_build_building("laboratory", 1):
                        self.build_nearby_drill("laboratory", "crystals")
                        return

                    if self.have_building_or_construction("laboratory", 1) and self.should_build_building("pump", 1):
                        self.build_drills("oil", 1)
                        return

                    if not self.have_building("pump", 1) and self.should_build_building("talos", 2):
                        self.build_nearby_drill("talos", "oil", 0, with_gap=True)
                        return
                    
                    if self.have_building("laboratory", 1) and self.have_building("drill", 3) and self.should_build_building("arsenal", 1):
                        self.build_nearby_drill("arsenal", "metal", 2)
                        return

                    if self.have_drill("oil", 1) and self.should_build_building("bot assembler", 1):
                        self.build_nearby_building("bot assembler", "laboratory", with_gap=c_strat)
                        return

                    if not self.have_building("bot assembler", 1) and self.should_build_building("talos", 3):
                        self.build_talos(with_gap=True, distance=200)
                        return

                    if self.have_building("bot assembler", 1) and self.have_building("concrete plant", 2) and not c_strat:
                        self.destroy_building("concrete plant")
                    
                    if len(self.atvs) < 9 and self.should_build_building("factory", 1):
                        self.build_nearby_drill("factory", "metal", 1, with_gap=True)
                    
                    if len(self.atvs) > 20 and self.have_building("factory", 1):
                        self.destroy_building("factory")
                    
                    if self.have_building_or_construction("bot assembler", 1) and self.have_building("concrete plant", 2):
                        self.destroy_building("concrete plant", 0)
                        return

                    # if self.have_building("bot assembler", 1) and self.have_jaggernaut(1) and self.should_build_building("bot assembler", 2):
                    #     self.build_nearby_building("bot assembler", "nucleus")
                    #     return

                    # if self.have_building("bot assembler", 2) and self.have_jaggernaut(3):
                    #     self.destroy_concrete_plant()

                    if not c_strat or not self.have_resources("metal", 4) or not self.have_resources("reinforced concrete", 4) or not self.have_jaggernaut(1):
                        return

                    if self.should_build_building("forgepress", 1):
                        # share metal with concrete plant temporarily
                        self.build_nearby_drill("forgepress", "metal", 2, with_gap=True)
                        return

                    if self.have_building("forgepress", 1) and self.should_build_building("pump", 2): 
                        self.build_drills("aether", 1)
                        return

                    if self.have_drill("aether", 1) and self.have_building("forgepress", 1) and self.should_build_building("generator", 1):                    
                        # built for armor plates from forgepress
                        self.build_nearby_building("generator", "nucleus", with_gap=True)
                        return

                    if self.have_building("generator", 1) and self.should_build_building("smelter", 1):
                        # share the same metal with the factory
                        # build from power cell
                        self.build_nearby_drill("smelter", "metal", 1, with_gap=True)
                        return

                    if self.have_drill("aether", 1) and self.have_building("generator", 1) and self.should_build_building("blender", 1):
                        self.build_nearby_drill("blender", "aether")
                        return

                    if self.have_building("blender", 1) and self.should_build_building("blender", 2):
                        self.build_nearby_drill("blender", "aether", with_gap=True)
                        return

                    if self.have_building("blender", 2) and self.should_build_building("blender", 3):
                        self.build_nearby_drill("blender", "aether", with_gap=True)
                        return

                    if self.have_building("smelter", 1) and self.should_build_building("forgepress", 2):
                        self.build_nearby_building("forgepress", "smelter", with_gap=True)
                        return
                    
                    if self.have_building_or_construction("generator", 1) and self.have_building("smelter", 1) and self.should_build_building("laboratory", 2):
                        self.build_nearby_building("laboratory", "smelter", with_gap=True)
                        return
                    
                    if self.have_building("blender", 3) and self.have_building("laboratory", 2) and self.should_build_building("laboratory", 3):
                        # quantum ray
                        self.build_nearby_building("laboratory", "generator")
                        return                    

                    if self.have_building_or_construction("laboratory", 3) and self.should_build_building("experimental assembler", 1):
                        self.build_nearby_building("experimental assembler", "smelter")
                        return

                    if self.have_building("experiental assembler", 1) and self.have_building("laboratory", 3):
                        print("Trying to destroy laboratory")
                        self.destroy_temporary_laboratory()
                        return
                    

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


# def _log_callback(self, data):
#     log_data = LogCallback.from_c(self._ffi, data)
#     skip_messages = [
#         "need to wait ",
#         "schedule: ",
#         "skipping ",
#     ]
#     for skip_message in skip_messages:
#         if log_data.message.startswith(skip_message):
#             return
#     print(log_data.message, flush=True)