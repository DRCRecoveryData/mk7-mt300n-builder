#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Author:   <you>
# License:  MIT License
# Original inspiration: Naqwada (Sweet Pineapple Builder)
# Docs:     Build WiFi Pineapple Mark VII firmware for single-radio
#           MediaTek MT7628 devices (GL.iNet MT300N-V2 and similar).
# Note:     FOR EDUCATIONAL PURPOSE ONLY.

from __future__ import print_function, unicode_literals
from termcolor import cprint
import subprocess
import hashlib
import random
import shutil
import time
import sys
import os

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MK7_FW_URL  = ("https://storage.googleapis.com/hak5-dl.appspot.com/"
               "wifipineapplemk7/firmwares/2.1.3-stable/"
               "upgrade-2.1.3-stable.2022101708401.bin")
MK7_FW_SHA  = "d8cae7ab5efa390b272f14d69c27a556b4689a47b339783e13cced73c6d1a444"

IB_URL = ("https://downloads.openwrt.org/releases/21.02.1/targets/"
          "ramips/mt76x8/openwrt-imagebuilder-21.02.1-ramips-mt76x8.Linux-x86_64.tar.xz")
IB_DIR = "openwrt-imagebuilder-21.02.1-ramips-mt76x8.Linux-x86_64"

PROFILE = "hak5_wifi-pineapple-mk7"
ROOT_PWD_HASH = "$1$TiQN6h88$b.ZEITsCk5a0UbfxvhISA1"   # password: root

WORK   = os.path.abspath("./cake")
FW_BIN = os.path.join(WORK, "mk7_fw.bin")
EXTRACT = os.path.join(WORK, "_mk7_fw.bin.extracted")
ROOTFS = os.path.join(EXTRACT, "squashfs-root")
OVERLAY = os.path.join(WORK, "overlay")

# Official MK7 package list, minus proprietary Hak5 packages that are
# already inside the overlay. Anything prefixed with '-' is excluded.
PACKAGE_LIST = " ".join([
    "at","autossh","base-files","bash","blockd","block-mount","busybox",
    "ca-bundle","ca-certificates","coreutils","coreutils-base64",
    "coreutils-sleep","curl","dbus","dnsmasq","e2fsprogs","ebtables",
    "ethtool","file","firewall","fstools","fwtool","getrandom","glib2",
    "hostapd-common","hostapd-utils","ip6tables","iptables",
    "iptables-mod-ipmark","iptables-mod-ipopt","iw","iwinfo","jshn",
    "jsonfilter","kmod-bluetooth","kmod-cfg80211","kmod-crypto-aead",
    "kmod-crypto-cmac","kmod-crypto-crc32c","kmod-crypto-ecb",
    "kmod-crypto-ecdh","kmod-crypto-hash","kmod-crypto-kpp",
    "kmod-crypto-manager","kmod-crypto-null","kmod-crypto-pcompress",
    "kmod-ebtables","kmod-fs-autofs4","kmod-fs-ext4","kmod-fs-ntfs",
    "kmod-fs-vfat","kmod-fuse","kmod-gpio-button-hotplug","kmod-hid",
    "kmod-i2c-core","kmod-i2c-mt7628","kmod-input-core","kmod-input-evdev",
    "kmod-ip6tables","kmod-ipt-compat-xtables","kmod-ipt-conntrack",
    "kmod-ipt-core","kmod-ipt-ipmark","kmod-ipt-ipopt","kmod-ipt-nat",
    "kmod-ipt-offload","kmod-leds-gpio","kmod-lib-crc16",
    "kmod-lib-crc-ccitt","kmod-libphy","kmod-mac80211","kmod-mii",
    "kmod-mmc","kmod-mt76","kmod-mt7601u","kmod-mt7603","kmod-mt76-core",
    "kmod-mt76-usb","kmod-mt76x02-common","kmod-mt76x02-usb","kmod-mt76x2",
    "kmod-mt76x2-common","kmod-mt76x2u","kmod-nf-conntrack",
    "kmod-nf-conntrack6","kmod-nf-flow","kmod-nf-ipt","kmod-nf-ipt6",
    "kmod-nf-nat","kmod-nf-reject","kmod-nf-reject6","kmod-nls-base",
    "kmod-nls-cp437","kmod-nls-iso8859-1","kmod-nls-utf8","kmod-ppp",
    "kmod-pppoe","kmod-pppox","kmod-regmap-core","kmod-scsi-core",
    "kmod-sdhci","kmod-sdhci-mt7620","kmod-slhc","kmod-usb2",
    "kmod-usb-acm","kmod-usb-core","kmod-usb-ehci","kmod-usb-net",
    "kmod-usb-net-asix","kmod-usb-net-asix-ax88179",
    "kmod-usb-net-rtl8152","kmod-usb-ohci","kmod-usb-storage",
    "libatomic1","libattr","libblkid1","libblobmsg-json20210516",
    "libbz2-1.0","libc","libcbor0","libcomerr0","libcurl4","libdbus",
    "libelf1","libevdev","libexpat","libext2fs2","libffi","libfido2-1",
    "libgcc1","libgmp10","libgnutls","libical","libip4tc2","libip6tc2",
    "libiwinfo20210430","libiwinfo-data","libjson-c5",
    "libjson-script20210516","liblzma","libmagic","libmbedtls12",
    "libncurses6","libnettle8","libnghttp2-14","libnl-core200",
    "libnl-genl200","libnl-tiny1","libopenssl1.1","libopenssl-conf",
    "libpcap1","libpcre","libpthread","libpython3-3.9","libreadline8",
    "librt","libsqlite3-0","libss2","libstdcpp6","libubox20210516",
    "libubus20210630","libuci20130104","libuclient20201210",
    "libudev-zero","libusb-1.0-0","libustream-openssl20201210",
    "libuuid1","libxtables12","logd","macchanger","msmtp",
    "mt7601u-firmware","mtd","nano","netifd","ntfs-3g","odhcp6c",
    "odhcpd-ipv6only","openssh-client","openssh-client-utils",
    "openssh-keygen","openssh-server","openssh-sftp-server",
    "openssl-util","openwrt-keyring","opkg","ppp","ppp-mod-pppoe",
    "procd","procps-ng","procps-ng-free","procps-ng-kill",
    "procps-ng-pgrep","procps-ng-pkill","procps-ng-ps",
    "procps-ng-snice","procps-ng-top","procps-ng-uptime",
    "procps-ng-watch","protobuf-lite","python3-base","python3-codecs",
    "python3-email","python3-light","python3-logging","python3-openssl",
    "python3-urllib","swconfig","tcpdump","terminfo","ubox","ubus",
    "ubusd","uci","uclibcxx","uclient-fetch","urandom-seed","urngd",
    "usbids","usbutils","usign","vim","wireless-regdb","wireless-tools",
    "wpad","zlib",
    # Exclusions — these conflict with the default profile or the overlay
    "-libustream-wolfssl","-libustream-wolfssl20201210",
    "-wpad-basic","-wpad-basic-wolfssl","-wpad-basic-mbedtls",
    "-wpad-wolfssl","-wpad-mbedtls",
])

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def banner():
    logo = r"""
                       ..
                      .::
              ..     .:::.
             .::.   .:::::.
            .::::. .:::::::.
           .::::::.:::::::::.
          .:::::::::::::::::::.
         .:::::::::::::::::::::.
         .:::::::::::::::::::::.
          .:::::::::::::::::::.
           ':::::::::::::::::'
             ':::::::::::::'
               ':::::::::'
                 ':::::'
                   ':
          W I F I   P I N E A P P L E
             M K 7  B U I L D E R
"""
    colors = ['red', 'green', 'cyan', 'yellow', 'blue', 'magenta']
    cprint(logo, random.choice(colors), attrs=['bold'])
    cprint("  Mark VII portability builder for MT7628 routers\n",
           'cyan', attrs=['bold'])


def step(msg):
    cprint("[*] " + msg, 'blue', attrs=['bold'])


def ok(msg):
    cprint("[+] " + msg, 'green', attrs=['bold'])


def warn(msg):
    cprint("[!] " + msg, 'yellow', attrs=['bold'])


def fail(msg):
    cprint("[x] " + msg, 'red', attrs=['bold'])
    sys.exit(1)


def run(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=False, **kw)

# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def check_dependencies():
    step("Checking host dependencies")
    required = ["binwalk", "wget", "gawk", "git", "tar",
                "make", "gcc", "python3", "openssl", "sasquatch"]
    missing = [p for p in required if shutil.which(p) is None]

    if missing:
        warn("Missing: " + ", ".join(missing))
        warn("Install with: sudo apt install -y binwalk wget gawk git tar "
             "build-essential python3 openssl")
        warn("For sasquatch, see README.md (build from source).")
        if "sasquatch" not in missing:
            return
        sys.exit(1)

    ok("All host dependencies present.")


def download_firmware():
    step("Downloading official Mark VII firmware (2.1.3-stable)")
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(FW_BIN):
        run(["wget", "-q", "-O", FW_BIN, MK7_FW_URL])
    if not os.path.exists(FW_BIN):
        fail("Download failed.")

    step("Verifying SHA256")
    h = hashlib.sha256(open(FW_BIN, 'rb').read()).hexdigest()
    if h != MK7_FW_SHA:
        fail("Checksum mismatch: got {}, expected {}".format(h, MK7_FW_SHA))
    ok("Firmware verified ({} bytes).".format(os.path.getsize(FW_BIN)))


def extract_firmware():
    step("Extracting firmware (binwalk + sasquatch)")
    if os.path.isdir(EXTRACT):
        shutil.rmtree(EXTRACT)
    run(["binwalk", "-eM", "--run-as=root", FW_BIN])
    if not os.path.isdir(ROOTFS):
        fail("Extraction did not produce {}".format(ROOTFS))
    ok("Extracted to {}".format(ROOTFS))

    # Confirm the OpenWrt release matches what we expect
    rel = os.path.join(ROOTFS, "etc", "openwrt_release")
    if os.path.exists(rel):
        for line in open(rel):
            if line.startswith("DISTRIB_"):
                cprint("     " + line.rstrip(), 'white')


def _copy(rel_path):
    """Copy a file/dir from ROOTFS into the overlay, preserving attributes."""
    src = os.path.join(ROOTFS, rel_path.lstrip('/'))
    dst = os.path.join(OVERLAY, rel_path.lstrip('/'))
    if not os.path.exists(src):
        warn("Not found in firmware: " + rel_path)
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(src):
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst, symlinks=True)
    else:
        shutil.copy2(src, dst, follow_symlinks=False)


def build_overlay():
    step("Building overlay directory")
    if os.path.isdir(OVERLAY):
        shutil.rmtree(OVERLAY)
    os.makedirs(OVERLAY)

    # Directories to copy wholesale
    for d in [
        "pineapple",
        "etc/pineapple",
        "etc/pineape",
        "usr/lib/pineapple",
        "lib/wifi",
    ]:
        _copy(d)

    # Individual files
    for f in [
        "etc/pineapple.rc",
        "etc/config/autossh",
        "etc/banner",
        "etc/opkg.conf",
        "etc/inittab",
        "etc/rc.local",
        "etc/shadow",
        "etc/ssh/sshd_config",
        "usr/bin/pineap",
        "usr/bin/aircrack-ng",
        "usr/sbin/aireplay-ng",
        "usr/sbin/airodump-ng",
        "usr/sbin/airmon-ng",
        "usr/sbin/C2CONNECT",
        "usr/sbin/C2DISCONNECT",
        "usr/sbin/C2EXFIL",
        "usr/sbin/C2GETCONFIG",
        "usr/sbin/C2NOTIFY",
        "usr/sbin/cc-client",
        "usr/sbin/pineapd",
        "usr/sbin/pineapd_wrapper",
        "usr/sbin/resetssids",
        "etc/init.d/atd",
        "etc/init.d/autossh",
        "etc/init.d/cc-client",
        "etc/init.d/pineapd",
        "etc/init.d/pineapple",
        "etc/init.d/resetssids",
        "etc/rc.d/S50atd",
        "etc/rc.d/S80autossh",
        "etc/rc.d/S90resetssids",
        "etc/rc.d/S99cc-client",
        "etc/rc.d/S99pineapd",
        "etc/rc.d/S99pineapple",
        "etc/uci-defaults/04_led_migration",
        "etc/uci-defaults/90-firewall.sh",
        "etc/uci-defaults/92-system.sh",
        "etc/uci-defaults/93-pineap.sh",
        "etc/uci-defaults/95-network.sh",
        "etc/uci-defaults/97-pineapple.sh",
    ]:
        _copy(f)

    # libwifi symlinks + actual
    for lib in ["libwifi.so", "libwifi.so.0", "libwifi.so.0.0.5"]:
        _copy("usr/lib/" + lib)

    ok("Overlay built ({} MB)".format(
        int(subprocess.check_output(["du","-sm",OVERLAY]).split()[0])))


def create_uci_wrapper():
    step("Installing uci wrapper (auto-creates missing radioN sections)")
    os.makedirs(os.path.join(OVERLAY, "sbin"), exist_ok=True)
    wrapper = r"""#!/bin/sh
# uci wrapper: auto-create wireless.radioN sections when they don't exist.
# Makes MK7 firmware work on single-radio hardware (MT300N-V2, etc.).

REAL_UCI=/sbin/uci.real

if [ "$1" = "set" ]; then
    key="${2%%=*}"
    case "$key" in
        *.*.*)
            config="${key%%.*}"
            rest="${key#*.}"
            section="${rest%%.*}"
            case "$section" in
                radio[0-9]*)
                    section_path="$config.$section"
                    if ! "$REAL_UCI" -q get "$section_path" >/dev/null 2>&1; then
                        "$REAL_UCI" add "$config" wifi-device >/dev/null 2>&1
                        "$REAL_UCI" rename "$config.@wifi-device[-1]=$section" >/dev/null 2>&1
                        "$REAL_UCI" set "$section_path.type=mac80211" >/dev/null 2>&1
                        "$REAL_UCI" set "$section_path.disabled=1" >/dev/null 2>&1
                        "$REAL_UCI" commit "$config" >/dev/null 2>&1
                    fi
                    ;;
            esac
            ;;
    esac
fi

exec "$REAL_UCI" "$@"
"""
    dest = os.path.join(OVERLAY, "sbin", "uci")
    with open(dest, "w") as f:
        f.write(wrapper)
    os.chmod(dest, 0o755)

    # Preserve the real uci binary
    real = os.path.join(ROOTFS, "sbin", "uci")
    if os.path.exists(real):
        shutil.copy2(real, os.path.join(OVERLAY, "sbin", "uci.real"))
        os.chmod(os.path.join(OVERLAY, "sbin", "uci.real"), 0o755)
    ok("uci wrapper installed at /sbin/uci (real at /sbin/uci.real)")


def create_wireless_stub():
    step("Writing default /etc/config/wireless with radio1 stub")
    os.makedirs(os.path.join(OVERLAY, "etc", "config"), exist_ok=True)
    wireless = """config wifi-device 'radio0'
\toption type 'mac80211'
\toption channel '1'
\toption hwmode '11g'
\toption path 'platform/10300000.wmac'
\toption htmode 'HT20'
\toption disabled '0'
\toption country 'US'

config wifi-device 'radio1'
\toption type 'mac80211'
\toption channel '36'
\toption hwmode '11a'
\toption path 'pci0000:00/0000:00:00.0/0000:00:01.0'
\toption htmode 'VHT80'
\toption disabled '1'
\toption country 'US'

config wifi-iface 'default_radio0'
\toption device 'radio0'
\toption network 'lan'
\toption mode 'ap'
\toption ssid 'Pineapple'
\toption encryption 'none'
\toption disabled '0'

config wifi-iface 'default_radio1'
\toption device 'radio1'
\toption network 'lan'
\toption mode 'ap'
\toption ssid 'Pineapple_5G'
\toption encryption 'none'
\toption disabled '1'
"""
    with open(os.path.join(OVERLAY, "etc", "config", "wireless"), "w") as f:
        f.write(wireless)
    ok("wireless stub installed (radio1 disabled)")


def patch_configs():
    step("Patching rc.local, pineapple.rc, 93-pineap.sh, shadow")

    # 1. rc.local — remove eMMC mmcblk0 sanity check
    rc = os.path.join(OVERLAY, "etc", "rc.local")
    content = open(rc).read()
    patched = r"""#!/bin/ash

# Compile Python Modules
python3 -m compileall

# Configure WiFi interfaces
wifi config > /etc/config/wireless
wifi

# Setup Cron
mkdir -p /etc/crontabs
touch /etc/crontabs/root
/etc/init.d/cron enable
/etc/init.d/cron start

# Clean up and finish
rm -rf /etc/pineapple/init

echo -e "bash /etc/pineapple.rc\n\n\n# Enter commands above this line\nexit 0" > /etc/rc.local

exit 0
"""
    if "mmcblk0" in content:
        open(rc, "w").write(patched)
        ok("rc.local: eMMC check removed")

    # 2. pineapple.rc — comment out usb on
    prc = os.path.join(OVERLAY, "etc", "pineapple.rc")
    if os.path.exists(prc):
        c = open(prc).read().replace("\nusb on\n", "\n# usb on\n")
        open(prc, "w").write(c)
        ok("pineapple.rc: 'usb on' commented out")

    # 3. 93-pineap.sh — wlan1mon → wlan0mon for MT300N-V2
    pineap = os.path.join(OVERLAY, "etc", "uci-defaults", "93-pineap.sh")
    if os.path.exists(pineap):
        c = open(pineap).read().replace("wlan1mon", "wlan0mon")
        open(pineap, "w").write(c)
        ok("93-pineap.sh: pineap_interface → wlan0mon")

    # 4. shadow — set root password
    shadow = os.path.join(OVERLAY, "etc", "shadow")
    lines = open(shadow).read().splitlines()
    newlines = []
    for line in lines:
        if line.startswith("root:"):
            parts = line.split(":")
            parts[1] = ROOT_PWD_HASH
            line = ":".join(parts)
        newlines.append(line)
    open(shadow, "w").write("\n".join(newlines) + "\n")
    ok("shadow: root password set ('root')")


def download_image_builder():
    step("Downloading OpenWrt 21.02.1 Image Builder (ramips/mt76x8)")
    tarball = os.path.join(WORK, "imagebuilder.tar.xz")
    if not os.path.exists(os.path.join(WORK, IB_DIR)):
        if not os.path.exists(tarball):
            run(["wget", "-q", "-O", tarball, IB_URL])
        run(["tar", "-xf", tarball, "-C", WORK])
    ok("Image Builder ready")


def patch_prereq_build():
    step("Patching prereq-build.mk for Python 3.10+")
    mk = os.path.join(WORK, IB_DIR, "include", "prereq-build.mk")
    if not os.path.exists(mk):
        fail("Missing " + mk)
    c = open(mk).read()
    if "Python 3\\.[0-9]+" not in c:
        c = c.replace(r"Python 3\.([5-9]|10)\.?", r"Python 3\.[0-9]+")
        open(mk, "w").write(c)
        ok("Python version regex widened")
    # Disable the distutils host check (removed in Python 3.12+)
    lines = c.splitlines()
    out = []
    for ln in lines:
        if "TestHostCommand,python3-distutils" in ln:
            out.append("#" + ln)
        else:
            out.append(ln)
    open(mk, "w").write("\n".join(out) + "\n")
    ok("python3-distutils check disabled")


def build_image():
    step("Building custom firmware ({} → {})".format(PROFILE, "MT300N-V2"))
    ib = os.path.join(WORK, IB_DIR)
    overlay_abs = OVERLAY
    cmd = (
        'make -C "{ib}" image '
        'PROFILE={profile} '
        'PACKAGES="{pkgs}" '
        'FILES="{ovl}/"'
    ).format(ib=ib, profile=PROFILE, pkgs=PACKAGE_LIST, ovl=overlay_abs)
    cprint("     " + cmd, 'white')
    r = run(cmd)
    if r.returncode != 0:
        fail("Build failed with code {}".format(r.returncode))
    ok("Image built")


def collect_output():
    step("Collecting output images")
    out = os.path.abspath("./output")
    os.makedirs(out, exist_ok=True)
    src = os.path.join(WORK, IB_DIR, "bin", "targets", "ramips", "mt76x8")
    if not os.path.isdir(src):
        fail("Image directory missing: " + src)
    for f in os.listdir(src):
        if f.endswith(".bin") or f.endswith(".manifest") or f == "sha256sums":
            shutil.copy2(os.path.join(src, f), out)
    for f in sorted(os.listdir(out)):
        cprint("     {:<70} {} bytes".format(
            f, os.path.getsize(os.path.join(out, f))), 'white')
    ok("Output in ./output/")


def cleanup():
    step("Cleaning intermediate files")
    for p in [os.path.join(WORK, "imagebuilder.tar.xz"),
              os.path.join(WORK, "_mk7_fw.bin.extracted"),
              os.path.join(WORK, IB_DIR)]:
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.isfile(p):
            os.remove(p)
    ok("Done")


def main():
    banner()
    cprint("Hi there — let's bake a Mark VII firmware for your MT7628 router.\n",
           'cyan', attrs=['bold'])
    time.sleep(1)

    try:
        check_dependencies()
        download_firmware()
        extract_firmware()
        build_overlay()
        create_uci_wrapper()
        create_wireless_stub()
        patch_configs()
        download_image_builder()
        patch_prereq_build()
        build_image()
        collect_output()
        cleanup()

        cprint("\n[🍍] Firmware ready — flash from Breed as 'firmware' layout.\n",
               'green', attrs=['bold'])
        cprint("[!]  No recovery-image step is required for the MT300N-V2.",
               'yellow', attrs=['bold'])
        cprint("[!]  Back up Breed eeprom.bin before flashing.\n",
               'yellow', attrs=['bold'])
    except KeyboardInterrupt:
        cprint("\n[!] Interrupted.", 'red', attrs=['bold'])
        sys.exit(1)


if __name__ == "__main__":
    main()
