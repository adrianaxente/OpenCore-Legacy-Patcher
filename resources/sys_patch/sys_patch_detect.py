# Hardware Detection Logic for Root Patching
# Returns a dictionary of patches with boolean values
# Used when supplying data to sys_patch.py
# Copyright (C) 2020-2022, Dhinak G, Mykola Grymalyuk

from resources import constants, device_probe, utilities, amfi_detect
from resources.sys_patch import sys_patch_helpers
from data import model_array, os_data, sip_data, sys_patch_dict, smbios_data, cpu_data

import py_sip_xnu
from pathlib import Path
import plistlib

class detect_root_patch:
    def __init__(self, model, versions):
        self.model = model
        self.constants: constants.Constants() = versions
        self.computer = self.constants.computer

        # GPU Patch Detection
        self.nvidia_tesla   = False
        self.kepler_gpu     = False
        self.nvidia_web     = False
        self.amd_ts1        = False
        self.amd_ts2        = False
        self.iron_gpu       = False
        self.sandy_gpu      = False
        self.ivy_gpu        = False
        self.haswell_gpu    = False
        self.broadwell_gpu  = False
        self.skylake_gpu    = False
        self.legacy_gcn     = False
        self.legacy_polaris = False
        self.legacy_vega    = False

        # Misc Patch Detection
        self.brightness_legacy         = False
        self.legacy_audio              = False
        self.legacy_wifi               = False
        self.legacy_gmux               = False
        self.legacy_keyboard_backlight = False
        self.legacy_uhci_ohci          = False

        # Patch Requirements
        self.amfi_must_disable   = False
        self.amfi_shim_bins      = False
        self.supports_metal      = False
        self.needs_nv_web_checks = False
        self.requires_root_kc    = False

        # Validation Checks
        self.sip_enabled     = False
        self.sbm_enabled     = False
        self.amfi_enabled    = False
        self.fv_enabled      = False
        self.dosdude_patched = False
        self.missing_kdk     = False
        self.has_network     = False

        self.missing_whatever_green = False
        self.missing_nv_web_nvram   = False
        self.missing_nv_web_opengl  = False
        self.missing_nv_compat      = False

    def detect_gpus(self):
        gpus = self.constants.computer.gpus
        non_metal_os = os_data.os_data.catalina
        for i, gpu in enumerate(gpus):
            if gpu.class_code and gpu.class_code != 0xFFFFFFFF:
                print(f"- Found GPU ({i}): {utilities.friendly_hex(gpu.vendor_id)}:{utilities.friendly_hex(gpu.device_id)}")
                if gpu.arch in [device_probe.NVIDIA.Archs.Tesla] and self.constants.force_nv_web is False:
                    if self.constants.detected_os > non_metal_os:
                        self.nvidia_tesla = True
                        self.amfi_must_disable = True
                        if os_data.os_data.ventura in self.constants.legacy_accel_support:
                            self.amfi_shim_bins = True
                        self.legacy_keyboard_backlight = self.check_legacy_keyboard_backlight()
                        self.requires_root_kc = True
                elif gpu.arch == device_probe.NVIDIA.Archs.Kepler and self.constants.force_nv_web is False:
                    if self.constants.detected_os > os_data.os_data.big_sur:
                        # Kepler drivers were dropped with Beta 7
                        # 12.0 Beta 5: 21.0.0 - 21A5304g
                        # 12.0 Beta 6: 21.1.0 - 21A5506j
                        # 12.0 Beta 7: 21.1.0 - 21A5522h
                        if (
                            self.constants.detected_os >= os_data.os_data.ventura or
                            (
                                "21A5506j" not in self.constants.detected_os_build and
                                self.constants.detected_os == os_data.os_data.monterey and
                                self.constants.detected_os_minor > 0
                            )
                        ):
                            self.kepler_gpu = True
                            self.supports_metal = True
                            if self.constants.detected_os >= os_data.os_data.ventura:
                                self.amfi_must_disable = True
                elif gpu.arch in [
                    device_probe.NVIDIA.Archs.Fermi,
                    device_probe.NVIDIA.Archs.Kepler,
                    device_probe.NVIDIA.Archs.Maxwell,
                    device_probe.NVIDIA.Archs.Pascal,
                ]:
                    if self.constants.detected_os > os_data.os_data.mojave:
                        self.nvidia_web = True
                        self.amfi_must_disable = True
                        if os_data.os_data.ventura in self.constants.legacy_accel_support:
                            self.amfi_shim_bins = True
                        self.needs_nv_web_checks = True
                        self.requires_root_kc = True
                elif gpu.arch == device_probe.AMD.Archs.TeraScale_1:
                    if self.constants.detected_os > non_metal_os:
                        self.amd_ts1 = True
                        self.amfi_must_disable = True
                        if os_data.os_data.ventura in self.constants.legacy_accel_support:
                            self.amfi_shim_bins = True
                        self.requires_root_kc = True
                elif gpu.arch == device_probe.AMD.Archs.TeraScale_2:
                    if self.constants.detected_os > non_metal_os:
                        self.amd_ts2 = True
                        self.amfi_must_disable = True
                        if os_data.os_data.ventura in self.constants.legacy_accel_support:
                            self.amfi_shim_bins = True
                        self.requires_root_kc = True
                elif gpu.arch in [
                    device_probe.AMD.Archs.Legacy_GCN_7000,
                    device_probe.AMD.Archs.Legacy_GCN_8000,
                    device_probe.AMD.Archs.Legacy_GCN_9000,
                    device_probe.AMD.Archs.Polaris,
                ]:
                    if self.constants.detected_os > os_data.os_data.monterey:
                        if self.constants.computer.rosetta_active is True:
                            continue

                        if gpu.arch == device_probe.AMD.Archs.Polaris:
                            # Check if host supports AVX2.0
                            # If not, enable legacy GCN patch
                            # MacBookPro13,3 does include an unsupported framebuffer, thus we'll patch to ensure
                            # full compatibility (namely power states, etc)
                            # Reference: https://github.com/dortania/bugtracker/issues/292
                            # TODO: Probe framebuffer families further
                            if self.model != "MacBookPro13,3":
                                if "AVX2" in self.constants.computer.cpu.leafs:
                                    continue
                                self.legacy_polaris = True
                            else:
                                self.legacy_gcn = True
                        else:
                            self.legacy_gcn = True
                        self.supports_metal = True
                        self.requires_root_kc = True
                        self.amfi_must_disable = True
                elif gpu.arch == device_probe.AMD.Archs.Vega:
                     if self.constants.detected_os > os_data.os_data.monterey:
                        if "AVX2" in self.constants.computer.cpu.leafs:
                            continue

                        self.legacy_vega = True
                        self.supports_metal = True
                        self.requires_root_kc = True
                        self.amfi_must_disable = True
                elif gpu.arch == device_probe.Intel.Archs.Iron_Lake:
                    if self.constants.detected_os > non_metal_os:
                        self.iron_gpu = True
                        self.amfi_must_disable = True
                        if os_data.os_data.ventura in self.constants.legacy_accel_support:
                            self.amfi_shim_bins = True
                        self.legacy_keyboard_backlight = self.check_legacy_keyboard_backlight()
                        self.requires_root_kc = True
                elif gpu.arch == device_probe.Intel.Archs.Sandy_Bridge:
                    if self.constants.detected_os > non_metal_os:
                        self.sandy_gpu = True
                        self.amfi_must_disable = True
                        if os_data.os_data.ventura in self.constants.legacy_accel_support:
                            self.amfi_shim_bins = True
                        self.legacy_keyboard_backlight = self.check_legacy_keyboard_backlight()
                        self.requires_root_kc = True
                elif gpu.arch == device_probe.Intel.Archs.Ivy_Bridge:
                    if self.constants.detected_os > os_data.os_data.big_sur:
                        self.ivy_gpu = True
                        if self.constants.detected_os >= os_data.os_data.ventura:
                            self.amfi_must_disable = True
                        self.supports_metal = True
                elif gpu.arch == device_probe.Intel.Archs.Haswell:
                    if self.constants.detected_os > os_data.os_data.monterey:
                        self.haswell_gpu = True
                        self.amfi_must_disable = True
                        self.supports_metal = True
                elif gpu.arch == device_probe.Intel.Archs.Broadwell:
                    if self.constants.detected_os > os_data.os_data.monterey:
                        self.broadwell_gpu = True
                        self.amfi_must_disable = True
                        self.supports_metal = True
                elif gpu.arch == device_probe.Intel.Archs.Skylake:
                    if self.constants.detected_os > os_data.os_data.monterey:
                        self.skylake_gpu = True
                        self.amfi_must_disable = True
                        self.supports_metal = True
        if self.supports_metal is True:
            # Avoid patching Metal and non-Metal GPUs if both present, prioritize Metal GPU
            # Main concerns are for iMac12,x with Sandy iGPU and Kepler dGPU
            self.nvidia_tesla = False
            self.nvidia_web = False
            self.amd_ts1 = False
            self.amd_ts2 = False
            self.iron_gpu = False
            self.sandy_gpu = False
            self.legacy_keyboard_backlight = False

        if self.legacy_gcn is True:
            # We can only support one or the other due to the nature of relying
            # on portions of the native AMD stack for Polaris and Vega
            # Thus we'll prioritize legacy GCN due to being the internal card
            # ex. MacPro6,1 and MacBookPro11,5 with eGPUs
            self.legacy_polaris = False
            self.legacy_vega = False

        if self.constants.detected_os <= os_data.os_data.monterey:
            # Always assume Root KC requirement on Monterey and older
            self.requires_root_kc = True
        else:
            if self.requires_root_kc is True:
                self.missing_kdk = not self.check_kdk()

        self.check_networking_support()


    def check_networking_support(self):
        # On macOS Ventura, networking support is required to download KDKs.
        # However for machines such as BCM94322, BCM94328 and Atheros chipsets,
        # users may only have wifi as their only supported network interface.
        # Thus we'll allow for KDK-less installs for these machines on first run.
        # On subsequent runs, we'll require networking to be enabled.

        if self.constants.detected_os < os_data.os_data.ventura:
            return
        if self.legacy_wifi is False:
            return
        if self.requires_root_kc is False:
            return
        if self.missing_kdk is False:
            return
        if self.has_network is True:
            return

        # Verify whether OCLP already installed network patches to the root volume
        # If so, require networking to be enabled (user just needs to connect to wifi)
        oclp_patch_path = "/System/Library/CoreServices/OpenCore-Legacy-Patcher.plist"
        if Path(oclp_patch_path).exists():
            oclp_plist = plistlib.load(open(oclp_patch_path, "rb"))
            if "Legacy Wireless" in oclp_plist:
                return

        # Due to the reliance of KDKs for most older patches, we'll allow KDK-less
        # installs for Legacy Wifi patches and remove others
        self.missing_kdk =      False
        self.requires_root_kc = False

        # Reset patches needing KDK
        self.nvidia_tesla              = False
        self.nvidia_web                = False
        self.amd_ts1                   = False
        self.amd_ts2                   = False
        self.iron_gpu                  = False
        self.sandy_gpu                 = False
        self.legacy_gcn                = False
        self.legacy_polaris            = False
        self.legacy_vega               = False
        self.brightness_legacy         = False
        self.legacy_audio              = False
        self.legacy_gmux               = False
        self.legacy_keyboard_backlight = False


    def check_dgpu_status(self):
        dgpu = self.constants.computer.dgpu
        if dgpu:
            if dgpu.class_code and dgpu.class_code == 0xFFFFFFFF:
                # If dGPU is disabled via class-codes, assume demuxed
                return False
            return True
        return False

    def detect_demux(self):
        # If GFX0 is missing, assume machine was demuxed
        # -wegnoegpu would also trigger this, so ensure arg is not present
        if not "-wegnoegpu" in (utilities.get_nvram("boot-args", decode=True) or ""):
            igpu = self.constants.computer.igpu
            dgpu = self.check_dgpu_status()
            if igpu and not dgpu:
                return True
        return False

    def check_legacy_keyboard_backlight(self):
        # iMac12,x+ have an 'ACPI0008' device, but it's not a keyboard backlight
        # Best to assume laptops will have a keyboard backlight
        if self.model.startswith("MacBook"):
            return self.constants.computer.ambient_light_sensor
        return False

    def check_nv_web_nvram(self):
        # First check boot-args, then dedicated nvram variable
        nv_on = utilities.get_nvram("boot-args", decode=True)
        if nv_on:
            if "nvda_drv_vrl=" in nv_on:
                return True
        nv_on = utilities.get_nvram("nvda_drv")
        if nv_on:
            return True
        return False

    def check_nv_web_opengl(self):
        # First check boot-args, then whether property exists on GPU
        nv_on = utilities.get_nvram("boot-args", decode=True)
        if nv_on:
            if "ngfxgl=" in nv_on:
                return True
        for gpu in self.constants.computer.gpus:
            if isinstance(gpu, device_probe.NVIDIA):
                if gpu.disable_metal is True:
                    return True
        return False

    def check_nv_compat(self):
        # Check for 'nv_web' in boot-args, then whether property exists on GPU
        nv_on = utilities.get_nvram("boot-args", decode=True)
        if nv_on:
            if "ngfxcompat=" in nv_on:
                return True
        for gpu in self.constants.computer.gpus:
            if isinstance(gpu, device_probe.NVIDIA):
                if gpu.force_compatible is True:
                    return True
        return False

    def check_whatevergreen(self):
        return utilities.check_kext_loaded("WhateverGreen", self.constants.detected_os)

    def check_kdk(self):
        if sys_patch_helpers.sys_patch_helpers(self.constants).determine_kdk_present() is None:
            return False
        return True

    def check_sip(self):
        if self.constants.detected_os > os_data.os_data.catalina:
            if self.nvidia_web is True:
                sip = sip_data.system_integrity_protection.root_patch_sip_big_sur_3rd_part_kexts
                sip_hex = "0xA03"
                sip_value = (
                    f"For Hackintoshes, please set csr-active-config to '030A0000' ({sip_hex})\nFor non-OpenCore Macs, please run 'csrutil disable' and \n'csrutil authenticated-root disable' in RecoveryOS"
                )
            elif self.constants.detected_os >= os_data.os_data.ventura:
                sip = sip_data.system_integrity_protection.root_patch_sip_ventura
                sip_hex = "0x803"
                sip_value = (
                    f"For Hackintoshes, please set csr-active-config to '03080000' ({sip_hex})\nFor non-OpenCore Macs, please run 'csrutil disable' and \n'csrutil authenticated-root disable' in RecoveryOS"
                )
            else:
                sip = sip_data.system_integrity_protection.root_patch_sip_big_sur
                sip_hex = "0x802"
                sip_value = (
                    f"For Hackintoshes, please set csr-active-config to '02080000' ({sip_hex})\nFor non-OpenCore Macs, please run 'csrutil disable' and \n'csrutil authenticated-root disable' in RecoveryOS"
                )
        else:
            sip = sip_data.system_integrity_protection.root_patch_sip_mojave
            sip_hex = "0x603"
            sip_value = f"For Hackintoshes, please set csr-active-config to '03060000' ({sip_hex})\nFor non-OpenCore Macs, please run 'csrutil disable' in RecoveryOS"
        return (sip, sip_value, sip_hex)

    def check_uhci_ohci(self):
        if self.constants.detected_os < os_data.os_data.ventura:
            return False

        for controller in self.constants.computer.usb_controllers:
            if (isinstance(controller, device_probe.XHCIController)):
                # Currently USB 1.1 patches are incompatible with USB 3.0 controllers
                # TODO: Downgrade remaining USB stack to ensure full support
                return False

        # If we're on a hackintosh, check for UHCI/OHCI controllers
        if self.constants.host_is_hackintosh is True:
            for controller in self.constants.computer.usb_controllers:
                if (
                    isinstance(controller, device_probe.UHCIController) or
                    isinstance(controller, device_probe.OHCIController)
                ):
                    return True
            return False

        if self.model not in smbios_data.smbios_dictionary:
            return False

        # If we're on a Mac, check for Penryn or older
        # This is due to Apple implementing an internal USB hub on post-Penryn (excluding MacPro4,1 and MacPro5,1)
        # Ref: https://techcommunity.microsoft.com/t5/microsoft-usb-blog/reasons-to-avoid-companion-controllers/ba-p/270710
        if (
            smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.cpu_data.penryn.value or \
            self.model in ["MacPro4,1", "MacPro5,1"]
        ):
            return True

        return False

    def detect_patch_set(self):
        self.has_network = utilities.verify_network_connection()

        if self.check_uhci_ohci() is True:
            self.legacy_uhci_ohci = True
            self.requires_root_kc = True

        if self.model in model_array.LegacyBrightness:
            if self.constants.detected_os > os_data.os_data.catalina:
                self.brightness_legacy = True

        if self.model in ["iMac7,1", "iMac8,1"] or (self.model in model_array.LegacyAudio and utilities.check_kext_loaded("AppleALC", self.constants.detected_os) is False):
            # Special hack for systems with botched GOPs
            # TL;DR: No Boot Screen breaks Lilu, therefore breaking audio
            if self.constants.detected_os > os_data.os_data.catalina:
                self.legacy_audio = True

        if (
            isinstance(self.constants.computer.wifi, device_probe.Broadcom)
            and self.constants.computer.wifi.chipset in [device_probe.Broadcom.Chipsets.AirPortBrcm4331, device_probe.Broadcom.Chipsets.AirPortBrcm43224]
        ) or (isinstance(self.constants.computer.wifi, device_probe.Atheros) and self.constants.computer.wifi.chipset == device_probe.Atheros.Chipsets.AirPortAtheros40):
            if self.constants.detected_os > os_data.os_data.big_sur:
                self.legacy_wifi = True
                if self.constants.detected_os >= os_data.os_data.ventura:
                    # Due to extracted frameworks for IO80211.framework and co, check library validation
                    self.amfi_must_disable = True

        # if self.model in ["MacBookPro5,1", "MacBookPro5,2", "MacBookPro5,3", "MacBookPro8,2", "MacBookPro8,3"]:
        if self.model in ["MacBookPro8,2", "MacBookPro8,3"]:
            # Sierra uses a legacy GMUX control method needed for dGPU switching on MacBookPro5,x
            # Same method is also used for demuxed machines
            # Note that MacBookPro5,x machines are extremely unstable with this patch set, so disabled until investigated further
            # Ref: https://github.com/dortania/OpenCore-Legacy-Patcher/files/7360909/KP-b10-030.txt
            if self.constants.detected_os > os_data.os_data.high_sierra:
                if self.model in ["MacBookPro8,2", "MacBookPro8,3"]:
                    # Ref: https://doslabelectronics.com/Demux.html
                    if self.detect_demux() is True:
                        self.legacy_gmux = True
                else:
                    self.legacy_gmux = True

        self.detect_gpus()

        self.root_patch_dict = {
            "Graphics: Nvidia Tesla":                      self.nvidia_tesla,
            "Graphics: Nvidia Kepler":                     self.kepler_gpu,
            "Graphics: Nvidia Web Drivers":                self.nvidia_web,
            "Graphics: AMD TeraScale 1":                   self.amd_ts1,
            "Graphics: AMD TeraScale 2":                   self.amd_ts2,
            "Graphics: AMD Legacy GCN":                    self.legacy_gcn,
            "Graphics: AMD Legacy Polaris":                self.legacy_polaris,
            "Graphics: AMD Legacy Vega":                   self.legacy_vega,
            "Graphics: Intel Ironlake":                    self.iron_gpu,
            "Graphics: Intel Sandy Bridge":                self.sandy_gpu,
            "Graphics: Intel Ivy Bridge":                  self.ivy_gpu,
            "Graphics: Intel Haswell":                     self.haswell_gpu,
            "Graphics: Intel Broadwell":                   self.broadwell_gpu,
            "Graphics: Intel Skylake":                     self.skylake_gpu,
            "Brightness: Legacy Backlight Control":        self.brightness_legacy,
            "Audio: Legacy Realtek":                       self.legacy_audio,
            "Networking: Legacy Wireless":                 self.legacy_wifi,
            "Miscellaneous: Legacy GMUX":                  self.legacy_gmux,
            "Miscellaneous: Legacy Keyboard Backlight":    self.legacy_keyboard_backlight,
            "Miscellaneous: Legacy USB 1.1":               self.legacy_uhci_ohci,
            "Settings: Requires AMFI exemption":           self.amfi_must_disable,
            "Settings: Supports Auxiliary Cache":          not self.requires_root_kc,
            "Settings: Kernel Debug Kit missing":          self.missing_kdk if self.constants.detected_os >= os_data.os_data.ventura.value else False,
            "Validation: Patching Possible":               self.verify_patch_allowed(),
            "Validation: Unpatching Possible":             self.verify_unpatch_allowed(),
            f"Validation: SIP is enabled (Required: {self.check_sip()[2]} or higher)":  self.sip_enabled,
            f"Validation: Currently Booted SIP: ({hex(py_sip_xnu.SipXnu().get_sip_status().value)})":         self.sip_enabled,
            "Validation: SecureBootModel is enabled":      self.sbm_enabled,
            f"Validation: {'AMFI' if self.constants.host_is_hackintosh is True or self.get_amfi_level_needed() > 2 else 'Library Validation'} is enabled":                 self.amfi_enabled if self.amfi_must_disable is True else False,
            "Validation: FileVault is enabled":            self.fv_enabled,
            "Validation: System is dosdude1 patched":      self.dosdude_patched,
            "Validation: WhateverGreen.kext missing":      self.missing_whatever_green if self.nvidia_web is True else False,
            "Validation: Force OpenGL property missing":   self.missing_nv_web_opengl  if self.nvidia_web is True else False,
            "Validation: Force compat property missing":   self.missing_nv_compat      if self.nvidia_web is True else False,
            "Validation: nvda_drv(_vrl) variable missing": self.missing_nv_web_nvram   if self.nvidia_web is True else False,
            "Validation: Network Connection Required":     (not self.has_network) if (self.requires_root_kc and self.missing_kdk and self.constants.detected_os >= os_data.os_data.ventura.value) else False,
        }

        return self.root_patch_dict

    def get_amfi_level_needed(self):
        if self.amfi_must_disable is True:
            if self.constants.detected_os > os_data.os_data.catalina:
                if self.constants.detected_os >= os_data.os_data.ventura:
                    if self.amfi_shim_bins is True:
                        # Currently we require AMFI outright disabled
                        # in Ventura to work with shim'd binaries
                        return 3
                return 1
        return 0

    def verify_patch_allowed(self, print_errors=False):
        sip_dict = self.check_sip()
        sip = sip_dict[0]
        sip_value = sip_dict[1]

        self.sip_enabled, self.sbm_enabled, self.fv_enabled, self.dosdude_patched = utilities.patching_status(sip, self.constants.detected_os)
        self.amfi_enabled = not amfi_detect.amfi_configuration_detection().check_config(self.get_amfi_level_needed())

        if self.nvidia_web is True:
            self.missing_nv_web_nvram   = not self.check_nv_web_nvram()
            self.missing_nv_web_opengl  = not self.check_nv_web_opengl()
            self.missing_nv_compat      = not self.check_nv_compat()
            self.missing_whatever_green = not self.check_whatevergreen()

        if print_errors is True:
            if self.sip_enabled is True:
                print("\nCannot patch! Please disable System Integrity Protection (SIP).")
                print("Disable SIP in Patcher Settings and Rebuild OpenCore\n")
                print("Ensure the following bits are set for csr-active-config:")
                print("\n".join(sip))
                print(sip_value)

            if self.sbm_enabled is True:
                print("\nCannot patch! Please disable Apple Secure Boot.")
                print("Disable SecureBootModel in Patcher Settings and Rebuild OpenCore")
                print("For Hackintoshes, set SecureBootModel to Disabled")

            if self.fv_enabled is True:
                print("\nCannot patch! Please disable FileVault.")
                print("For OCLP Macs, please rebuild your config with 0.2.5 or newer")
                print("For others, Go to System Preferences -> Security and disable FileVault")

            if self.amfi_enabled is True and self.amfi_must_disable is True:
                print("\nCannot patch! Please disable AMFI.")
                print("For Hackintoshes, please add amfi_get_out_of_my_way=1 to boot-args")

            if self.dosdude_patched is True:
                print("\nCannot patch! Detected machine has already been patched by another patcher")
                print("Please ensure your install is either clean or patched with OpenCore Legacy Patcher")

            if self.nvidia_web is True:
                if self.missing_nv_web_opengl is True:
                    print("\nCannot patch! Force OpenGL property missing")
                    print("Please ensure ngfxgl=1 is set in boot-args")

                if self.missing_nv_compat is True:
                    print("\nCannot patch! Force Nvidia compatibility property missing")
                    print("Please ensure ngfxcompat=1 is set in boot-args")

                if self.missing_nv_web_nvram is True:
                    print("\nCannot patch! nvda_drv(_vrl) variable missing")
                    print("Please ensure nvda_drv_vrl=1 is set in boot-args")

                if self.missing_whatever_green is True:
                    print("\nCannot patch! WhateverGreen.kext missing")
                    print("Please ensure WhateverGreen.kext is installed")

            if (not self.has_network) if (self.requires_root_kc and self.missing_kdk and self.constants.detected_os >= os_data.os_data.ventura.value) else False:
                print("\nCannot patch! Network Connection Required")
                print("Please ensure you have an active internet connection")

        if any(
            [
                # General patch checks
                self.sip_enabled, self.sbm_enabled, self.fv_enabled, self.dosdude_patched,

                # non-Metal specific
                self.amfi_enabled if self.amfi_must_disable is True else False,

                # Web Driver specific
                self.missing_nv_web_nvram   if self.nvidia_web is True  else False,
                self.missing_nv_web_opengl  if self.nvidia_web is True  else False,
                self.missing_nv_compat      if self.nvidia_web is True  else False,
                self.missing_whatever_green if self.nvidia_web is True  else False,

                # KDK specific
                (not self.has_network) if (self.requires_root_kc and self.missing_kdk and self.constants.detected_os >= os_data.os_data.ventura.value) else False
            ]
        ):
            return False
        else:
            return True

    def verify_unpatch_allowed(self, print_errors=False):
        # Must be called after verify_patch_allowed
        return not self.sip_enabled

    def generate_patchset(self, hardware_details):
        all_hardware_patchset = sys_patch_dict.SystemPatchDictionary(self.constants.detected_os, self.constants.detected_os_minor, self.constants.legacy_accel_support)
        required_patches = {}
        utilities.cls()
        print("- The following patches will be applied:")
        if hardware_details["Graphics: Intel Ironlake"] is True:
            required_patches.update({"Non-Metal Common": all_hardware_patchset["Graphics"]["Non-Metal Common"]})
            required_patches.update({"WebKit Monterey Common": all_hardware_patchset["Graphics"]["WebKit Monterey Common"]})
            required_patches.update({"Intel Ironlake": all_hardware_patchset["Graphics"]["Intel Ironlake"]})
        if hardware_details["Graphics: Intel Sandy Bridge"] is True:
            required_patches.update({"Non-Metal Common": all_hardware_patchset["Graphics"]["Non-Metal Common"]})
            required_patches.update({"Non-Metal ColorSync Workaround": all_hardware_patchset["Graphics"]["Non-Metal ColorSync Workaround"]})
            required_patches.update({"High Sierra GVA": all_hardware_patchset["Graphics"]["High Sierra GVA"]})
            required_patches.update({"WebKit Monterey Common": all_hardware_patchset["Graphics"]["WebKit Monterey Common"]})
            required_patches.update({"Intel Sandy Bridge": all_hardware_patchset["Graphics"]["Intel Sandy Bridge"]})
        if hardware_details["Graphics: Intel Ivy Bridge"] is True:
            required_patches.update({"Metal 3802 Common": all_hardware_patchset["Graphics"]["Metal 3802 Common"]})
            required_patches.update({"Catalina GVA": all_hardware_patchset["Graphics"]["Catalina GVA"]})
            required_patches.update({"Monterey OpenCL": all_hardware_patchset["Graphics"]["Monterey OpenCL"]})
            required_patches.update({"Big Sur OpenCL": all_hardware_patchset["Graphics"]["Big Sur OpenCL"]})
            required_patches.update({"WebKit Monterey Common": all_hardware_patchset["Graphics"]["WebKit Monterey Common"]})
            required_patches.update({"Intel Ivy Bridge": all_hardware_patchset["Graphics"]["Intel Ivy Bridge"]})
        if hardware_details["Graphics: Intel Haswell"] is True:
            required_patches.update({"Metal 3802 Common": all_hardware_patchset["Graphics"]["Metal 3802 Common"]})
            required_patches.update({"Monterey GVA": all_hardware_patchset["Graphics"]["Monterey GVA"]})
            required_patches.update({"Monterey OpenCL": all_hardware_patchset["Graphics"]["Monterey OpenCL"]})
            required_patches.update({"Intel Haswell": all_hardware_patchset["Graphics"]["Intel Haswell"]})
        if hardware_details["Graphics: Intel Broadwell"] is True:
            required_patches.update({"Monterey GVA": all_hardware_patchset["Graphics"]["Monterey GVA"]})
            required_patches.update({"Monterey OpenCL": all_hardware_patchset["Graphics"]["Monterey OpenCL"]})
            required_patches.update({"Intel Broadwell": all_hardware_patchset["Graphics"]["Intel Broadwell"]})
        if hardware_details["Graphics: Intel Skylake"] is True:
            required_patches.update({"Monterey GVA": all_hardware_patchset["Graphics"]["Monterey GVA"]})
            required_patches.update({"Monterey OpenCL": all_hardware_patchset["Graphics"]["Monterey OpenCL"]})
            required_patches.update({"Intel Skylake": all_hardware_patchset["Graphics"]["Intel Skylake"]})
        if hardware_details["Graphics: Nvidia Tesla"] is True:
            required_patches.update({"Non-Metal Common": all_hardware_patchset["Graphics"]["Non-Metal Common"]})
            required_patches.update({"WebKit Monterey Common": all_hardware_patchset["Graphics"]["WebKit Monterey Common"]})
            required_patches.update({"Nvidia Tesla": all_hardware_patchset["Graphics"]["Nvidia Tesla"]})
        if hardware_details["Graphics: Nvidia Web Drivers"] is True:
            required_patches.update({"Non-Metal Common": all_hardware_patchset["Graphics"]["Non-Metal Common"]})
            required_patches.update({"Non-Metal IOAccelerator Common": all_hardware_patchset["Graphics"]["Non-Metal IOAccelerator Common"]})
            required_patches.update({"Non-Metal CoreDisplay Common": all_hardware_patchset["Graphics"]["Non-Metal CoreDisplay Common"]})
            required_patches.update({"WebKit Monterey Common": all_hardware_patchset["Graphics"]["WebKit Monterey Common"]})
            required_patches.update({"Nvidia Web Drivers": all_hardware_patchset["Graphics"]["Nvidia Web Drivers"]})
            required_patches.update({"Non-Metal Enforcement": all_hardware_patchset["Graphics"]["Non-Metal Enforcement"]})
        if hardware_details["Graphics: Nvidia Kepler"] is True:
            required_patches.update({"Revert Metal Downgrade": all_hardware_patchset["Graphics"]["Revert Metal Downgrade"]})
            required_patches.update({"Metal 3802 Common": all_hardware_patchset["Graphics"]["Metal 3802 Common"]})
            required_patches.update({"Catalina GVA": all_hardware_patchset["Graphics"]["Catalina GVA"]})
            required_patches.update({"Monterey OpenCL": all_hardware_patchset["Graphics"]["Monterey OpenCL"]})
            required_patches.update({"Big Sur OpenCL": all_hardware_patchset["Graphics"]["Big Sur OpenCL"]})
            required_patches.update({"WebKit Monterey Common": all_hardware_patchset["Graphics"]["WebKit Monterey Common"]})
            required_patches.update({"Nvidia Kepler": all_hardware_patchset["Graphics"]["Nvidia Kepler"]})
            for gpu in self.constants.computer.gpus:
                # Handle mixed GPU situations (ie. MacBookPro11,3: Haswell iGPU + Kepler dGPU)
                if gpu.arch == device_probe.Intel.Archs.Haswell:
                    if "Catalina GVA" in required_patches:
                        del(required_patches["Catalina GVA"])
                    break
        if hardware_details["Graphics: AMD TeraScale 1"] is True:
            required_patches.update({"Non-Metal Common": all_hardware_patchset["Graphics"]["Non-Metal Common"]})
            required_patches.update({"WebKit Monterey Common": all_hardware_patchset["Graphics"]["WebKit Monterey Common"]})
            required_patches.update({"AMD TeraScale Common": all_hardware_patchset["Graphics"]["AMD TeraScale Common"]})
            required_patches.update({"AMD TeraScale 1": all_hardware_patchset["Graphics"]["AMD TeraScale 1"]})
        if hardware_details["Graphics: AMD TeraScale 2"] is True:
            required_patches.update({"Non-Metal Common": all_hardware_patchset["Graphics"]["Non-Metal Common"]})
            required_patches.update({"Non-Metal IOAccelerator Common": all_hardware_patchset["Graphics"]["Non-Metal IOAccelerator Common"]})
            required_patches.update({"WebKit Monterey Common": all_hardware_patchset["Graphics"]["WebKit Monterey Common"]})
            required_patches.update({"AMD TeraScale Common": all_hardware_patchset["Graphics"]["AMD TeraScale Common"]})
            required_patches.update({"AMD TeraScale 2": all_hardware_patchset["Graphics"]["AMD TeraScale 2"]})
            if self.constants.allow_ts2_accel is False or self.constants.detected_os not in self.constants.legacy_accel_support:
                # TeraScale 2 MacBooks with faulty GPUs are highly prone to crashing with AMDRadeonX3000 attached
                # Additionally, AMDRadeonX3000 requires IOAccelerator downgrade which is not installed without 'Non-Metal IOAccelerator Common'
                del(required_patches["AMD TeraScale 2"]["Install"]["/System/Library/Extensions"]["AMDRadeonX3000.kext"])
        if hardware_details["Graphics: AMD Legacy GCN"] is True or hardware_details["Graphics: AMD Legacy Polaris"] is True:
            required_patches.update({"Revert Metal Downgrade": all_hardware_patchset["Graphics"]["Revert Metal Downgrade"]})
            required_patches.update({"Monterey GVA": all_hardware_patchset["Graphics"]["Monterey GVA"]})
            required_patches.update({"Monterey OpenCL": all_hardware_patchset["Graphics"]["Monterey OpenCL"]})
            if hardware_details["Graphics: AMD Legacy GCN"] is True:
                required_patches.update({"AMD Legacy GCN": all_hardware_patchset["Graphics"]["AMD Legacy GCN"]})
            else:
                required_patches.update({"AMD Legacy Polaris": all_hardware_patchset["Graphics"]["AMD Legacy Polaris"]})
            if "AVX2" not in self.constants.computer.cpu.leafs:
                required_patches.update({"AMD OpenCL": all_hardware_patchset["Graphics"]["AMD OpenCL"]})
        if hardware_details["Graphics: AMD Legacy Vega"] is True:
            required_patches.update({"Monterey GVA": all_hardware_patchset["Graphics"]["Monterey GVA"]})
            required_patches.update({"Monterey OpenCL": all_hardware_patchset["Graphics"]["Monterey OpenCL"]})
            required_patches.update({"AMD Legacy Vega": all_hardware_patchset["Graphics"]["AMD Legacy Vega"]})
            required_patches.update({"AMD OpenCL": all_hardware_patchset["Graphics"]["AMD OpenCL"]})
            if hardware_details["Graphics: AMD Legacy GCN"] is True:
                required_patches.update({"AMD Legacy Vega Extended": all_hardware_patchset["Graphics"]["AMD Legacy Vega Extended"]})
        if hardware_details["Brightness: Legacy Backlight Control"] is True:
            required_patches.update({"Legacy Backlight Control": all_hardware_patchset["Brightness"]["Legacy Backlight Control"]})
        if hardware_details["Audio: Legacy Realtek"] is True:
            if self.model in ["iMac7,1", "iMac8,1"]:
                required_patches.update({"Legacy Realtek": all_hardware_patchset["Audio"]["Legacy Realtek"]})
            else:
                required_patches.update({"Legacy Non-GOP": all_hardware_patchset["Audio"]["Legacy Non-GOP"]})
        if hardware_details["Networking: Legacy Wireless"] is True:
            required_patches.update({"Legacy Wireless": all_hardware_patchset["Networking"]["Legacy Wireless"]})
            required_patches.update({"Legacy Wireless Extended": all_hardware_patchset["Networking"]["Legacy Wireless Extended"]})
        if hardware_details["Miscellaneous: Legacy GMUX"] is True:
            required_patches.update({"Legacy GMUX": all_hardware_patchset["Miscellaneous"]["Legacy GMUX"]})
        if hardware_details["Miscellaneous: Legacy Keyboard Backlight"] is True:
            required_patches.update({"Legacy Keyboard Backlight": all_hardware_patchset["Miscellaneous"]["Legacy Keyboard Backlight"]})
        if hardware_details["Miscellaneous: Legacy USB 1.1"] is True:
            required_patches.update({"Legacy USB 1.1": all_hardware_patchset["Miscellaneous"]["Legacy USB 1.1"]})

        if required_patches:
            host_os_float = float(f"{self.constants.detected_os}.{self.constants.detected_os_minor}")

            # Prioritize Monterey GVA patches
            if "Catalina GVA" in required_patches and "Monterey GVA" in required_patches:
                del(required_patches["Catalina GVA"])

            for patch_name in list(required_patches):
                patch_os_min_float = float(f'{required_patches[patch_name]["OS Support"]["Minimum OS Support"]["OS Major"]}.{required_patches[patch_name]["OS Support"]["Minimum OS Support"]["OS Minor"]}')
                patch_os_max_float = float(f'{required_patches[patch_name]["OS Support"]["Maximum OS Support"]["OS Major"]}.{required_patches[patch_name]["OS Support"]["Maximum OS Support"]["OS Minor"]}')
                if (host_os_float < patch_os_min_float or host_os_float > patch_os_max_float):
                    del(required_patches[patch_name])
                else:
                    if required_patches[patch_name]["Display Name"]:
                        print(f"  - {required_patches[patch_name]['Display Name']}")
        else:
            print("  - No patch sets found for booted model")

        return required_patches