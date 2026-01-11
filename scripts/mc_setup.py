#!/usr/bin/env python

from urllib.request import urlopen, Request, urlretrieve
from urllib.parse import quote
import argparse, json, re, os, shutil, sys
from pathlib import Path, PosixPath
from datetime import datetime as dt

def _col(colour):
    templ = "\033[%sm%%s\033[0m" % colour if sys.stdout.isatty() else "%s"
    return lambda text: templ % text


yellow = _col("33;1")
blue = _col("34;1")
green = _col("32;1")
red = _col("31;1")


class MinecraftConfiguration():
    def __init__(self):
        base_url = "https://api.modrinth.com/v2"
        headers = {'User-Agent': 'antroy/puffer_scripts'}
        self.config_file = PosixPath("~/.puffer_scripts_config.json").expanduser()
        with open(self.config_file) as fh:
            self.config = json.load(fh)

        self.instances_dir = Path(self.config["instances_dir"])
        self.base_url = base_url
        self.headers = headers
        self.args = self._args()
        self.mods = {mod["slug"]: mod for mod in self.config["mods"]}

    def _args(self):
        parser = argparse.ArgumentParser(prog=sys.argv[0], description='Set up a minecraft instance')

        parser.add_argument("-v", "--version")
        parser.add_argument("-i", "--instance")
        parser.add_argument("-s", "--search", help="Search for the mod slug for a mod")
        parser.add_argument("-l", "--list", action="store_true", default=False, help="List mods in instance")
        parser.add_argument("-x", "--exclude-managed", action="store_true", default=False, help="For List command, only show unmanaged mods (mods not in the puffer_scripts_config file)")
        parser.add_argument("-u", "--update", action="store_true", default=False, help="Update the mods, backing up old mods in a timestamped folder")
        parser.add_argument("--find-unmanaged", action="store_true", default=False, help="Look for mods in the mods folder that aren't managed in the config. Prompts to add the correct one from a Modrinth search")

        args = parser.parse_args()

        return args

    def get_instance_data(self):
        instances = self.config["instances"]
        instance_map = {i: instance for i, instance in enumerate(instances)}
        for i, instance in enumerate(instances):
            print("%-2s) %s" % (i + 1, instance))

        return instances[instance_map[int(input("Choose an instance:")) - 1]]


    def call_modrinth(self, path):
        url = f"{self.base_url}/{path}"
        with urlopen(Request(url, headers=self.headers)) as fh:
            try:
                raw_data = fh.read()
                return json.loads(raw_data)
            except:
                print(f"ERROR: [{url}]; {raw_data}")


    def search(self, project):
        path = f"search?query={project}"
        data = self.call_modrinth(path)
        hits = data.get("hits", [])
        if not hits:
            print("No results")

        for i, hit in enumerate(hits):
            hit["index"] = i + 1
            print(f"%(index)2s) %(title)s [%(project_type)s]: By '%(author)s'. Slug: %(slug)s" % hit)
        
        return hits

    def list(self):
        mod_names = [mod.name for mod in self.mod_dir.glob("*.jar")]
        print(self.mod_dir)
        for mod in sorted(mod_names, key=lambda m: m.lower()):
            if not self.args.exclude_managed or not any([mod.lower().startswith(m.get("prefix", m["slug"])) for m in self.mods.values()]):
                print(mod)

    def get_url_for_latest_mod(self, slug, version):
        query = f'loaders=[%22fabric%22]&game_versions=[%22{version}%22]'
        path = f'project/{slug}/version?{query}'
        data = self.call_modrinth(path)
        if not data:
            print(f"ERROR: Modrinth Data not found for '{slug}'")
            return
        latest = data[0]["files"][0]
        return {"file": latest["filename"], "url": latest["url"]}


    def latest_plugin_info(self, instance, mod_list):
        print("Getting mod info from Modrinth...")
        downloads = {slug: self.get_url_for_latest_mod(slug, instance["version"]) for slug in mod_list}

        return downloads


    def get_current_mods(self):
        current_mods = list(self.mod_dir.glob("*.jar"))
        managed_mods = {}
        for mod_slug, mod in self.mods.items():
            for mod_path in current_mods:
                mod_name = mod_path.name.lower()
                prefix = mod.get("prefix", mod_slug)
                if mod_name.startswith(prefix.lower()):
                    managed_mods[mod_slug] = mod_path
                    break

        return managed_mods

    def run(self):
        if self.args.search:
            self.search(quote(self.args.search))
            sys.exit(0)
        
        instance = self.args.instance
        instance_data = None
        if instance:
            instance_data = self.config["instances"].get(instance)
            if not instance_data:
                print(f"No such instance '{instance_dir}'")
                instance_data = self.get_instance_data()
        else:
            instance_data = self.get_instance_data()

        self.instance_dir =  self.instances_dir / instance_data["instance_dir"]
        minecraft_dir = self.instance_dir if self.config["is_server"] else self.instance_dir / ".minecraft"
        self.mod_dir = minecraft_dir / "mods"

        if self.args.find_unmanaged:
            self.find_unmanaged()
            sys.exit(0)
        
        if self.args.list:
            self.list()
            sys.exit(0)

        changes = self.analyse_mods(instance_data) 

        if self.args.update:
            self.install_updates(changes)

    def install_updates(self, changes):
        print("-" * 80)
        if not input("Proceed with update? ([y]/n)").strip().lower() == "y":
            return
        updates = [change for change in changes if change["action"] == "update"]
        additions = [change for change in changes if change["action"] == "add"]

        if updates:
            backup_folder = self.mod_dir / dt.now().strftime("%y-%m-%y_%H-%M-%S")
            print(f"Backing up old mods to {backup_folder}")
            backup_folder.mkdir()
            for update in updates:
                (self.mod_dir / update["current"]).move(backup_folder / update["current"])
                new_mod = self.mod_dir / update["latest"]
                print(f"Installing {update['latest']}")
                urlretrieve(update["url"], new_mod)
        if additions:
            for addition in additions:
                new_mod = self.mod_dir / addition["latest"]
                print(f"Adding {addition['latest']}")
                urlretrieve(addition["url"], new_mod)

        
    def analyse_mods(self, instance_data):
        latest_plugins = self.latest_plugin_info(instance_data, self.mods)
        current_plugins = self.get_current_mods()
        changes = []

        for mod in self.mods:
            current = current_plugins[mod].name if mod in current_plugins else None
            latest = latest_plugins[mod] if mod in latest_plugins else None

            if not latest:
                print(f"Mod for {mod} not found in Modrinth")
                continue

            latest_file = latest['file']
            latest_url = latest['url']

            if not current:
                print(red(f"Mod for {mod} not installed locally. Latest: {latest_file}"))
                changes.append({"mod": mod, "action": "add", "latest": latest_file, "url": latest_url})
            elif current == latest_file:
                print(green(f"{mod} is up to date!"))
            else:
                print(yellow(f"Mod {mod} can be updated.\n  Current: {current}\n  Latest:  {latest_file}"))
                changes.append({"mod": mod, "action": "update", "current": current, "latest": latest_file, "url": latest_url})

        return changes

    
    def find_unmanaged(self):
        current_mods = list(self.mod_dir.glob("*.jar"))
        managed_mods = self.get_current_mods()

        unmanaged_mods = sorted(list(set(current_mods) - set(managed_mods.values())), key=lambda m: m.name.lower())
        mods_to_add_to_config = []

        for mod in unmanaged_mods:
            m = re.match(r"(.*?)(?:-fabric)?-\d+(?:\.\d+)+.*\.jar", mod.name)
            if m:
                search_term = m[1]
                results = self.search(quote(search_term))

                if results:
                    choice = input(yellow(f"\nChoose the correct mod for {mod.name}. Enter if no results are correct: ")).strip()
                    if choice.isnumeric() and int(choice) > 0 and int(choice) <= len(results):
                        result = results[int(choice) - 1]
                        prefix = search_term if not search_term == result["slug"] else None
                        mods_to_add_to_config.append({"slug": result["slug"]})
                        if prefix:
                            mods_to_add_to_config[-1]["prefix"] = prefix
            else:
                print(f"Cannot parse {mod}")
        
        self.update_config(mods_to_add_to_config)

    def update_config(self, mods_to_add):
        self.config["mods"].extend(mods_to_add)
        self.config["mods"].sort(key=lambda mod: mod["slug"])

        self.config_file.rename(Path(str(self.config_file) + ".bak"))
        with open(self.config_file, "w") as fh:
            json.dump(self.config, fh, indent=2)

if __name__ == "__main__":
    minecraft_config = MinecraftConfiguration()
    minecraft_config.run()
