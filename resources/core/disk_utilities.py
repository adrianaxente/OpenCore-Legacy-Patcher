# Base class device like objects like disk, partition, etc...
# Copyright (C) 2022-2023, Adrian Axente

import plistlib
import subprocess

from abc import ABC
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from data import os_data

@dataclass(frozen=False)
class DeviceInfo(ABC):
    identifier: str
    name: str
    size: int

@dataclass(frozen=False)
class PartitionInfo(DeviceInfo):
    filesystem: str
    type: str
    mount_point: str

@dataclass(frozen=False)
class DiskInfo(DeviceInfo):
    device_node: str
    is_ejectable: bool
    is_internal: bool
    is_removable: bool
    is_virtual_or_physical: bool
    is_whole_disk: bool
    partitions: Iterable[PartitionInfo] = ()

def get_partition_info(identifier):
    partition_info = plistlib.loads(subprocess.run(f"diskutil info -plist {identifier}".split(), stdout=subprocess.PIPE).stdout.decode().strip().encode())
    return PartitionInfo(
        identifier = identifier,
        name = partition_info.get("VolumeName", ""),
        size =  partition_info["TotalSize"],
        filesystem = partition_info.get("FilesystemType", partition_info["Content"]),
        type = partition_info["Content"],
        mount_point = Path(partition_info["MountPoint"]) if partition_info["MountPoint"] else None)

def get_disk_info(identifier):
    disk_info = plistlib.loads(subprocess.run(f"diskutil info -plist {identifier}".split(), stdout=subprocess.PIPE).stdout.decode().strip().encode())
    return DiskInfo(
        identifier = identifier,
        name = disk_info["MediaName"],
        size = disk_info["TotalSize"],
        device_node = disk_info["DeviceNode"],
        is_ejectable = disk_info["Ejectable"],
        is_internal = disk_info["Internal"],
        is_removable =  disk_info["Removable"],
        is_virtual_or_physical = disk_info["VirtualOrPhysical"],
        is_whole_disk = disk_info["WholeDisk"])

def get_all_disks_infos():
    # TODO: AllDisksAndPartitions is not supported in Snow Leopard and older
    try:
        # High Sierra and newer
        disks = plistlib.loads(subprocess.run("diskutil list -plist physical".split(), stdout=subprocess.PIPE).stdout.decode().strip().encode())
    except ValueError:
        # Sierra and older
        disks = plistlib.loads(subprocess.run("diskutil list -plist".split(), stdout=subprocess.PIPE).stdout.decode().strip().encode())
    for disk in disks["AllDisksAndPartitions"]:
        try:
            disk_info = get_disk_info(disk["DeviceIdentifier"])
            disk_info.partitions = (get_partition_info(partition['DeviceIdentifier']) for partition in disk["Partitions"])
            yield disk_info
        except KeyError:
            # Avoid crashing with CDs installed
            continue

def mount_device(identifier, constants):
    if constants.detected_os >= os_data.os_data.el_capitan and not constants.recovery_status:
        # TODO: Apple Script fails in Yosemite(?) and older
        args = [
            "osascript",
            "-e",
            f'''do shell script "diskutil mount {identifier}"'''
            f' with prompt "OpenCore Legacy Patcher needs administrator privileges to mount {identifier}."'
            " with administrator privileges"
            " without altering line endings",
        ]
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        result = subprocess.run(f"diskutil mount {identifier}".split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # if result.returncode != 0:
    #     if "execution error" in result.stderr.decode() and result.stderr.decode().strip()[-5:-1] == "-128":
    #         raise Exception()

    return result

def unmount_device(mount_point):
    return subprocess.run(["diskutil", "umount", mount_point], stdout=subprocess.PIPE).stdout.decode().strip().encode()