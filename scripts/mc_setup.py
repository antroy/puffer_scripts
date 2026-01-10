#!/usr/bin/env python

from urllib.request import urlopen, Request, urlretrieve
from urllib.parse import quote
import argparse, json, re, os, shutil, sys
from pathlib import Path

class MinecraftConfiguration():
    def __init__(self):
        base_url = "https://api.modrinth.com/v2"
        headers = {'User-Agent': 'antroy/puffer_scripts'}
        config_file = "~/.puffer_scripts_config.json"
        with open(os.path.expanduser(config_file)) as fh:
            self.config = json.load(fh)

        self.instances_dir = Path(self.config["instances_dir"])
        self.base_url = base_url
        self.headers = headers
        self.args = self._args()

    def _args(self):
        parser = argparse.ArgumentParser(prog=sys.argv[0], description='Set up a minecraft instance')

        parser.add_argument("-v", "--version")
        parser.add_argument("-i", "--instance")
        parser.add_argument("-s", "--search", help="Search for the mod slug for a mod")

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
        print("Slug:", data["hits"][0]["slug"])
        for hit in data['hits']:
            print("%(title)s [%(project_type)s]: By '%(author)s'. Slug: %(slug)s" % hit)


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
        print("Getting mod info from Modrinth... Instance: ", instance)
        downloads = {slug: self.get_url_for_latest_mod(slug, instance["version"]) for slug in mod_list}

        for slug, download in downloads.items():
            print(f"Latest download for {slug}: {download["file"]}")
        
        return downloads

    def get_current_mods(self, instance, mod_list):
        minecraft_dir = self.instance_dir if self.config["is_server"] else self.instance_dir / ".minecraft"
        mod_dir = minecraft_dir / "mods"

        current_mods = list(mod_dir.glob("*.jar"))
        managed_mods = {}
        for mod in mod_list:
            for mod_path in current_mods:
                if mod_path.name.lower().startswith(mod):
                    managed_mods[mod] = mod_path
                    break

        for mod, path in managed_mods.items():
            print(f"Current {mod}:", path.name)

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

        mods = self.config["mods"]
        latest_plugins = self.latest_plugin_info(instance_data, mods)
        current_plugins = self.get_current_mods(instance_data, mods)

        for mod in mods:
            current = current_plugins[mod].name
            latest = latest_plugins[mod]['file']
            print(f"Mod {mod}: Current: {current}; Latest: {latest}")


if __name__ == "__main__":
    minecraft_config = MinecraftConfiguration()
    minecraft_config.run()
