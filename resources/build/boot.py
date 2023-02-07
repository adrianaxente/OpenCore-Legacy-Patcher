# Class for generating OpenCore Bootloader configuration 
# Copyright (C) 2022-2023, Adrian Axente

from dataclasses import dataclass
import ntpath
from typing import Iterable

from resources import constants
from resources.core import disk_utilities
from resources.core.disk_utilities import PartitionInfo
from pathlib import Path

@dataclass(frozen=True)
class BlessOverrideEntry:
    name: str
    file: Path
    value: str

class build_boot:
    def __init__(self, model, versions, config):
        self.model = model
        self.constants: constants.Constants = versions
        self.config = config
        self.computer = self.constants.computer

    def __get_all_internal_efi_partitions__(self) -> Iterable[PartitionInfo]:
        all_internal_disks = (disk for disk in disk_utilities.get_all_disks_infos() if disk.is_internal and not disk.is_removable and not disk.is_ejectable)
        all_internal_partitions = (partition for disk in all_internal_disks for partition in disk.partitions)
        return (partition for partition in all_internal_partitions if partition.type and partition.type.upper() == "EFI")

    def _get_bootloader_entries(self, mount_point: Path):
        efi_path = mount_point / Path("EFI")

        for f in efi_path.rglob("*"):
            found_entry = next(
                filter(
                    lambda e: f.match(e["Pattern"]),
                    self.constants.known_boot_loader_efi_file_patterns),
                None)
            if found_entry is not None:
                yield BlessOverrideEntry(
                    name = found_entry["Name"],
                    file = f,
                    value = str(ntpath.normpath(Path("/") / f.relative_to(mount_point)))
                )

    def build(self):

        found_bootloader_entries: list[BlessOverrideEntry] = []
        
        all_internal_efi_partitions = list(self.__get_all_internal_efi_partitions__())

        # TODO: Avoid asking the root password for every efi partition instead ask it for all only once
        for partition in all_internal_efi_partitions:
            print(f'- Mounting EFI partition {partition.identifier} and searching known boot loaders')
            mount_result = disk_utilities.mount_device(partition.identifier, self.constants)
            # TODO: Handle the mount result properly
            if mount_result.returncode == 0:
                partition_info = disk_utilities.get_partition_info(partition.identifier)
                found_bootloader_entries.extend(self._get_bootloader_entries(partition_info.mount_point))
                # TODO: Handle the unmount result properly
                unmount_result = disk_utilities.unmount_device(partition_info.mount_point)
            else:
                print(f"An error occurred while mounting disk: {partition.identifier}, {mount_result}")

        new_boot_loader_entries = [
            fbe for fbe in found_bootloader_entries if fbe.value not in self.config["Misc"]["BlessOverride"]]

        if len(new_boot_loader_entries) > 0:
            print("- Found The Following Boot Loaders:")
            for i, entry in enumerate(new_boot_loader_entries):
                print(
                    f"\t{i + 1}. {entry.name} in: {entry.file}")

            if self.constants.gui_mode is False:
                choice = input(
                    "\nWould you like OpenCore to use found boot loaders?(y/n): ")
                if not choice in ["y", "Y", "Yes", "yes"]:
                    return False

            print("- Configuring Found BootLoaders")
            new_bless_overrides = list(
                map(lambda nbe: nbe.value, new_boot_loader_entries))
            self.config["Misc"]["BlessOverride"] = new_bless_overrides + \
                self.config["Misc"]["BlessOverride"]