# Post Installation after disk installation of OpenCore files to ESP
# Usage solely for TUI
# Copyright (C) 2022-2023, Adrian Axente

import plistlib
import posixpath
import ntpath
from pathlib import Path, WindowsPath
from resources import constants, utilities


class tui_post_installation:
    def __init__(self, mount_path: Path, versions):
        self.mount_path = mount_path
        self.efi_path = self.mount_path / Path("EFI")
        self.constants: constants.Constants = versions

    def post_install(self):
        utilities.header(["\nPerforming post installation"])

        plist_path = self.efi_path / Path("OC/config.plist")

        try:
            plist = plistlib.load(plist_path.open("rb"))
        except Exception:
            print("- Failed to read Open Core property list")
            raise

        self.configure_efi_boot_loaders(plist)

        try:
            plistlib.dump(plist, plist_path.open("wb"), sort_keys=True)
        except PermissionError:
            print("- Failed to write to Open Core property file")
            raise

    def configure_efi_boot_loaders(self, plist):

        found_boot_loader_entries = []

        for f in self.efi_path.rglob("*"):
            found_entry = next(
                filter(
                    lambda e: f.match(e["Pattern"]),
                    self.constants.known_boot_loader_efi_file_patterns),
                None)
            if found_entry is not None:
                found_boot_loader_entries.append(
                    {
                        "Name": found_entry["Name"],
                        "File": f,
                        "BlessOverride": str(ntpath.normpath(Path("/") / f.relative_to(self.mount_path)))
                    }
                )

        new_boot_loader_entries = [
            fbe for fbe in found_boot_loader_entries if fbe["BlessOverride"] not in plist["Misc"]["BlessOverride"]]

        if len(new_boot_loader_entries) > 0:
            print("- Found The Following Boot Loaders:")
            for bi in range(0, len(new_boot_loader_entries)):
                print(
                    f"\t{bi + 1}. {new_boot_loader_entries[bi]['Name']} in: {new_boot_loader_entries[bi]['File']}")

            if self.constants.gui_mode is False:
                choice = input(
                    "\nWould you like OpenCore to use found boot loaders?(y/n): ")
                if not choice in ["y", "Y", "Yes", "yes"]:
                    return False

            print("- Configuring Found BootLoaders")
            new_bless_overrides = list(
                map(lambda nbe: nbe["BlessOverride"], new_boot_loader_entries))
            plist["Misc"]["BlessOverride"] = new_bless_overrides + \
                plist["Misc"]["BlessOverride"]

        return True
