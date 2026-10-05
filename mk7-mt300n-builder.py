#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Author:   <you>
# License:  MIT License
# Based on: Sweet-Pineapple-Builder by Naqwada (Necrum Security Labs)
# Note:     FOR EDUCATIONAL PURPOSE ONLY.
#
# Builds WiFi Pineapple Mark VII 2.1.3-stable firmware for single-radio
# MediaTek MT7628 routers (GL.iNet MT300N-V2, etc.).
#
# Two build modes:
#   QUICK  — Image Builder only. ~5 minutes. Reset button/LEDs non-functional
#            (use SSH workaround for setup wizard).
#   FULL   — Patches the kernel DTS so reset button + LEDs work natively.
#            First run: 1-3 hours (compiles OpenWrt from source). Subsequent
#            runs: ~5 minutes (kernel cached).
#
# After building, automatically hands off to mk7-runner.py which boots the
# firmware in QEMU and opens the dashboard in Firefox.

from __future__ import print_function, unicode_literals
from termcolor import cprint
import subprocess
import hashlib
import time
import pwd
import sys
import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
WORK_DIR    = os.path.join(SCRIPT_DIR, "cake")
FW_BIN      = os.path.join(WORK_DIR, "mk7fw.bin")
EXTRACT_DIR = os.path.join(WORK_DIR, "_mk7fw.bin.extracted")
ROOTFS_DIR  = os.path.join(EXTRACT_DIR, "squashfs-root")
OVERLAY_DIR = os.path.join(WORK_DIR, "overlay")
IB_TARBALL  = os.path.join(WORK_DIR, "openwrt-imagebuilder.tar.xz")
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, "customFW")
RUNNER_PY   = os.path.join(SCRIPT_DIR, "mk7-runner.py")
SRC_DIR     = os.path.join(WORK_DIR, "openwrt-src")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MK7_FW_URL = ("https://storage.googleapis.com/hak5-dl.appspot.com/"
              "wifipineapplemk7/firmwares/2.1.3-stable/"
              "upgrade-2.1.3-stable.2022101708401.bin")
MK7_FW_SHA = "d8cae7ab5efa390b272f14d69c27a556b4689a47b339783e13cced73c6d1a444"

IB_URL = ("https://downloads.openwrt.org/releases/21.02.1/targets/"
          "ramips/mt76x8/openwrt-imagebuilder-21.02.1-ramips-mt76x8.Linux-x86_64.tar.xz")
IB_DIR_NAME = "openwrt-imagebuilder-21.02.1-ramips-mt76x8.Linux-x86_64"
IB_DIR      = os.path.join(WORK_DIR, IB_DIR_NAME)

SRC_GIT_URL = "https://git.openwrt.org/openwrt/openwrt.git"
SRC_GIT_REF = "v21.02.1"

PROFILE       = "hak5_wifi-pineapple-mk7"
ROOT_PWD_HASH = "$1$TiQN6h88$b.ZEITsCk5a0UbfxvhISA1"   # password: root

# MT300N-V2 GPIO overrides for the DTS patch
MT300N_RESET_GPIO   = 38
MT300N_LED_BLUE     = 42
MT300N_LED_GREEN    = 43
MT300N_LED_RED      = 44

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def banner():
    logo = r"""
                       .::
                     .::::.
                    .::::::.
                   .::::::::.
                  .::::::::::.
                 .::::::::::::.
                .::::::::::::::.
                .::::::::::::::.
                 .::::::::::::.
                  .::::::::::.
                   .::::::::.
                    .::::::.
                     .::::.
                       ':
              ,,        ,,         ,,

      M K 7   P O R T A B I L I T Y   B U I L D E R
              Sweet Pineapple  v2.2
"""
    cprint(logo, 'green', attrs=['bold'])


def step(msg):  cprint('[+] ' + msg, 'blue',   attrs=['bold'])
def ok(msg):    cprint('[+] ' + msg, 'green',  attrs=['bold'])
def warn(msg):  cprint('[!] ' + msg, 'yellow', attrs=['bold'])
def fail(msg):  cprint('[x] ' + msg, 'red',    attrs=['bold']); sys.exit(1)


def run(cmd, **kw):
    kw.setdefault("shell", isinstance(cmd, str))
    return subprocess.run(cmd, **kw)


def _which(prog):
    for p in os.environ.get("PATH", "").split(os.pathsep):
        full = os.path.join(p, prog)
        if os.path.exists(full) and os.access(full, os.X_OK):
            return full
    return None


# ---------------------------------------------------------------------------
# Build mode selection
# ---------------------------------------------------------------------------

def selectBuildMode():
    print()
    cprint("  +-- BUILD MODE ------------------------------------------------+",
           'cyan', attrs=['bold'])
    cprint("  | [1] QUICK  — Image Builder only, ~5 min                     |",
           'white')
    cprint("  |              Reset button/LEDs still broken                 |",
           'white')
    cprint("  |              Use SSH to bypass setup wizard                 |",
           'white')
    cprint("  |                                                             |",
           'white')
    cprint("  | [2] FULL   — Patch kernel DTS (reset + LEDs work)           |",
           'white')
    cprint("  |              First run: 1-3 hours (compiles OpenWrt)        |",
           'white')
    cprint("  |              Cached after that: ~5 min per build            |",
           'white')
    cprint("  +-------------------------------------------------------------+",
           'cyan', attrs=['bold'])

    while True:
        try:
            ans = input("  ? Choose mode [1-2, default 1]: ").strip() or "1"
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if ans == "1":
            return "quick"
        if ans == "2":
            return "full"
        cprint("  [!] Invalid selection.", 'yellow')


def selectTarget():
    choices = [
        ("1", "mt300n-v2",      "GL.iNet MT300N-V2 (32 MB flash, single 2.4 GHz radio)"),
        ("2", "mt300n-v2-mini", "GL.iNet MT300N-V2 Mini"),
        ("3", "generic-mt7628", "Generic MT7628 single-radio board"),
    ]
    print()
    cprint("  +-- SELECT TARGET ---------------------------------------------+",
           'cyan', attrs=['bold'])
    for key, name, desc in choices:
        cprint("  | [{}] {:<17} {}".format(key, name, desc), 'white')
    cprint("  +---------------------------------------------------------------+",
           'cyan', attrs=['bold'])

    while True:
        try:
            ans = input("  ? Choose target [1-3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        for key, name, _ in choices:
            if ans == key or ans == name:
                return {"target": name}
        cprint("  [!] Invalid selection.", 'yellow')


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

def checkDependencies(mode):
    step("Checking host dependencies ...")
    required = ["binwalk", "wget", "gawk", "git", "tar",
                "make", "gcc", "openssl", "sasquatch"]
    missing = [p for p in required if not _which(p)]

    if mode == "full":
        required_full = ["rsync", "python3", "unzip", "ncursesw5-config"]
        for p in required_full:
            if not _which(p) and not os.path.exists("/usr/include/ncursesw/"):
                warn("FULL mode may need: " + p)

    if missing:
        warn("Missing: " + ", ".join(missing))
        cprint("    sudo apt install binwalk wget gawk git build-essential python3 openssl",
               'cyan')
        cprint("    sasquatch: https://github.com/devttys0/sasquatch", 'cyan')
        if "sasquatch" in missing:
            fail("Cannot continue without sasquatch.")
    ok("Dependencies satisfied.")


# ---------------------------------------------------------------------------
# Firmware download & extraction
# ---------------------------------------------------------------------------

def downloadPineappleFw():
    os.makedirs(WORK_DIR, exist_ok=True)
    step("Downloading WiFi Pineapple Mark VII firmware ...")
    if not os.path.exists(FW_BIN):
        cprint("[+] GET " + MK7_FW_URL, 'cyan')
        run('wget {} -O {}'.format(MK7_FW_URL, FW_BIN), shell=True)
    if not os.path.exists(FW_BIN):
        fail("Download failed.")

    step("Verifying SHA256 ...")
    h = hashlib.sha256(open(FW_BIN, 'rb').read()).hexdigest()
    if h != MK7_FW_SHA:
        fail("SHA256 mismatch:\n  expected {}\n  got      {}".format(MK7_FW_SHA, h))
    ok("Firmware verified.")


def unpackPineappleFw():
    step("Unpacking firmware ...")
    if os.path.isdir(EXTRACT_DIR):
        run('rm -rf ' + EXTRACT_DIR, shell=True)
    if pwd.getpwuid(os.getuid())[0] == 'root':
        run('binwalk -eM --run-as=root ' + FW_BIN, shell=True)
    else:
        run('binwalk -eM ' + FW_BIN, shell=True)
    if not os.path.isdir(ROOTFS_DIR):
        fail("Rootfs not found. Install sasquatch.")
    ok("Firmware unpacked.")


# ---------------------------------------------------------------------------
# Overlay extraction & patches
# ---------------------------------------------------------------------------

def extractPineappleOverlay():
    step("Extracting overlay ...")
    dirs = ["/pineapple", "/etc/pineapple", "/etc/pineape",
            "/usr/lib/pineapple", "/lib/wifi"]
    files = [
        "/etc/pineapple.rc", "/etc/config/autossh", "/etc/banner",
        "/etc/opkg.conf", "/etc/inittab", "/etc/rc.local", "/etc/shadow",
        "/etc/ssh/sshd_config",
        "/usr/bin/pineap", "/usr/bin/aircrack-ng",
        "/usr/sbin/aireplay-ng", "/usr/sbin/airodump-ng", "/usr/sbin/airmon-ng",
        "/usr/sbin/C2CONNECT", "/usr/sbin/C2DISCONNECT", "/usr/sbin/C2EXFIL",
        "/usr/sbin/C2GETCONFIG", "/usr/sbin/C2NOTIFY",
        "/usr/sbin/cc-client", "/usr/sbin/pineapd", "/usr/sbin/pineapd_wrapper",
        "/usr/sbin/resetssids",
        "/etc/init.d/atd", "/etc/init.d/autossh", "/etc/init.d/cc-client",
        "/etc/init.d/pineapd", "/etc/init.d/pineapple", "/etc/init.d/resetssids",
        "/etc/rc.d/S50atd", "/etc/rc.d/S80autossh", "/etc/rc.d/S90resetssids",
        "/etc/rc.d/S99cc-client", "/etc/rc.d/S99pineapd", "/etc/rc.d/S99pineapple",
        "/etc/uci-defaults/04_led_migration", "/etc/uci-defaults/90-firewall.sh",
        "/etc/uci-defaults/92-system.sh", "/etc/uci-defaults/93-pineap.sh",
        "/etc/uci-defaults/95-network.sh", "/etc/uci-defaults/97-pineapple.sh",
        "/usr/lib/libwifi.so", "/usr/lib/libwifi.so.0", "/usr/lib/libwifi.so.0.0.5",
    ]

    if os.path.isdir(OVERLAY_DIR):
        run('rm -rf ' + OVERLAY_DIR, shell=True)
    os.makedirs(OVERLAY_DIR, exist_ok=True)

    for path in dirs + files:
        src = ROOTFS_DIR + path
        dst = OVERLAY_DIR + path
        if not os.path.exists(src):
            warn("not in rootfs: " + path)
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        run('cp -a {} {}'.format(src, dst), shell=True)
    ok("Overlay extracted.")


def applyPortabilityPatches():
    step("Applying portability patches ...")

    # 1. uci wrapper
    os.makedirs(os.path.join(OVERLAY_DIR, "sbin"), exist_ok=True)
    wrapper = """#!/bin/sh
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
    with open(os.path.join(OVERLAY_DIR, "sbin", "uci"), "w") as f:
        f.write(wrapper)
    os.chmod(os.path.join(OVERLAY_DIR, "sbin", "uci"), 0o755)
    real_uci_src = os.path.join(ROOTFS_DIR, "sbin", "uci")
    if os.path.exists(real_uci_src):
        run('cp -a {} {}'.format(real_uci_src,
            os.path.join(OVERLAY_DIR, "sbin", "uci.real")), shell=True)
        os.chmod(os.path.join(OVERLAY_DIR, "sbin", "uci.real"), 0o755)
    ok("uci wrapper installed.")

    # 2. wireless stub with radio1
    os.makedirs(os.path.join(OVERLAY_DIR, "etc", "config"), exist_ok=True)
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
    with open(os.path.join(OVERLAY_DIR, "etc", "config", "wireless"), "w") as f:
        f.write(wireless)
    ok("wireless stub installed.")

    # 3. rc.local — remove eMMC check
    rc = os.path.join(OVERLAY_DIR, "etc", "rc.local")
    if os.path.exists(rc):
        if "mmcblk0" in open(rc).read():
            open(rc, "w").write("""#!/bin/ash

python3 -m compileall
wifi config > /etc/config/wireless
wifi

mkdir -p /etc/crontabs
touch /etc/crontabs/root
/etc/init.d/cron enable
/etc/init.d/cron start

rm -rf /etc/pineapple/init

echo -e "bash /etc/pineapple.rc\\n\\n\\n# Enter commands above this line\\nexit 0" > /etc/rc.local

exit 0
""")
            ok("rc.local: eMMC check removed.")

    # 4. pineapple.rc — comment out usb on
    prc = os.path.join(OVERLAY_DIR, "etc", "pineapple.rc")
    if os.path.exists(prc):
        c = open(prc).read().replace("\nusb on\n", "\n# usb on\n")
        open(prc, "w").write(c)
        ok("pineapple.rc: usb-on neutralized.")

    # 5. 93-pineap.sh
    pineap = os.path.join(OVERLAY_DIR, "etc", "uci-defaults", "93-pineap.sh")
    if os.path.exists(pineap):
        c = open(pineap).read().replace("wlan1mon", "wlan0mon")
        open(pineap, "w").write(c)
        ok("93-pineap.sh: pineap_interface → wlan0mon.")

    # 6. shadow — set root password
    shadow = os.path.join(OVERLAY_DIR, "etc", "shadow")
    if os.path.exists(shadow):
        lines = open(shadow).read().splitlines()
        out = []
        for line in lines:
            if line.startswith("root:"):
                parts = line.split(":")
                parts[1] = ROOT_PWD_HASH
                line = ":".join(parts)
            out.append(line)
        open(shadow, "w").write("\n".join(out) + "\n")
        ok("shadow: root password set.")

    ok("All portability patches applied.")


# ---------------------------------------------------------------------------
# Image Builder
# ---------------------------------------------------------------------------

def downloadOpenwrtImageBuilder():
    os.makedirs(WORK_DIR, exist_ok=True)
    if os.path.isdir(IB_DIR):
        ok("Image Builder cached.")
        return
    step("Downloading OpenWrt Image Builder ...")
    if not os.path.exists(IB_TARBALL):
        run('wget {} -O {}'.format(IB_URL, IB_TARBALL), shell=True)
    if not os.path.exists(IB_TARBALL):
        fail("Download failed.")
    ok("Image Builder downloaded.")


def extractOpenwrtImageBuilder():
    step("Extracting Image Builder ...")
    run('tar -xf {} -C {}'.format(IB_TARBALL, WORK_DIR), shell=True)
    if not os.path.isdir(IB_DIR):
        fail("Extraction failed.")
    ok("Image Builder extracted.")


def patchPrereqBuild():
    step("Patching prereq-build.mk for Python 3.12+ ...")
    mk = os.path.join(IB_DIR, "include", "prereq-build.mk")
    if not os.path.exists(mk):
        warn("prereq-build.mk not found.")
        return
    c = open(mk).read()
    c = c.replace(r"Python 3\.([5-9]|10)\.?", r"Python 3\.[0-9]+")
    lines = c.splitlines()
    out = []
    for ln in lines:
        if "TestHostCommand,python3-distutils" in ln and not ln.strip().startswith("#"):
            out.append("#" + ln)
        else:
            out.append(ln)
    open(mk, "w").write("\n".join(out) + "\n")
    ok("prereq-build.mk patched.")


# ---------------------------------------------------------------------------
# Kernel build with DTS patch (FULL mode)
# ---------------------------------------------------------------------------

def buildPatchedKernel():
    step("FULL mode: building kernel with MT300N-V2 DTS patches ...")

    vmlinux = os.path.join(SRC_DIR,
        "build_dir/target-mipsel_24kc_musl/linux-ramips_mt76x8/vmlinux")

    if os.path.exists(vmlinux):
        ok("Cached patched kernel found — skipping source build.")
        return vmlinux

    # 1. Clone source (shallow)
    if not os.path.isdir(SRC_DIR):
        step("Cloning OpenWrt {} source (this is a large download) ...".format(SRC_GIT_REF))
        run("git clone --depth 1 --branch {} {} {}".format(
            SRC_GIT_REF, SRC_GIT_URL, SRC_DIR), shell=True)
        step("Updating feeds ...")
        run("cd {0} && ./scripts/feeds update -a && ./scripts/feeds install -a"
            .format(SRC_DIR), shell=True)

    # 2. Patch the MK7 DTS
    step("Patching MK7 DTS with MT300N-V2 GPIOs ...")
    dts = os.path.join(SRC_DIR,
        "target/linux/ramips/dts/mt7628an_hak5_wifi-pineapple-mk7.dts")

    if not os.path.exists(dts):
        # Try alternate filename
        alt = os.path.join(SRC_DIR,
            "target/linux/ramips/dts/mt7628an_hak5_wifi_pineapple-mk7.dts")
        if os.path.exists(alt):
            dts = alt
        else:
            fail("DTS not found. Check:\n  " + dts)

    # Backup
    run('cp {} {}.orig'.format(dts, dts), shell=True)

    # Apply GPIO overrides
    sed_ops = [
        # Reset button: gpio 11 → gpio 38
        (r'<&gpio 11 GPIO_ACTIVE_LOW>', '<&gpio 38 GPIO_ACTIVE_LOW>'),
        (r'<&gpio1 11 GPIO_ACTIVE_LOW>', '<&gpio 38 GPIO_ACTIVE_LOW>'),
        # LEDs: MK7 gpio 0/2/3 → MT300N-V2 gpio 44/43/42
        (r'<&gpio 0 GPIO_ACTIVE_HIGH>', '<&gpio 44 GPIO_ACTIVE_LOW>'),
        (r'<&gpio 2 GPIO_ACTIVE_HIGH>', '<&gpio 43 GPIO_ACTIVE_LOW>'),
        (r'<&gpio 3 GPIO_ACTIVE_HIGH>', '<&gpio 42 GPIO_ACTIVE_LOW>'),
        (r'<&gpio 0 GPIO_ACTIVE_LOW>', '<&gpio 44 GPIO_ACTIVE_LOW>'),
        (r'<&gpio 2 GPIO_ACTIVE_LOW>', '<&gpio 43 GPIO_ACTIVE_LOW>'),
        (r'<&gpio 3 GPIO_ACTIVE_LOW>', '<&gpio 42 GPIO_ACTIVE_LOW>'),
    ]
    for old, new in sed_ops:
        run("sed -i 's|{}|{}|g' {}".format(old, new, dts), shell=True)

    # Verify
    try:
        hits = int(subprocess.check_output(
            ["grep", "-cE", "gpio 38|gpio 42|gpio 43|gpio 44", dts]
        ).decode().strip())
    except Exception:
        hits = 0

    if hits < 4:
        warn("DTS patch applied only {} times — expected >= 4.".format(hits))
        warn("Original DTS format may differ. Check: " + dts)
        warn("Continuing anyway.")
    else:
        ok("DTS patched ({} GPIO overrides applied).".format(hits))

    # 3. Configure
    step("Configuring build for hak5_wifi-pineapple-mk7 ...")
    with open(os.path.join(SRC_DIR, ".config"), "w") as f:
        f.write("\n".join([
            "CONFIG_TARGET_ramips=y",
            "CONFIG_TARGET_ramips_mt76x8=y",
            "CONFIG_TARGET_ramips_mt76x8_DEVICE_hak5_wifi-pineapple-mk7=y",
            "CONFIG_DEVEL=y",
            "CONFIG_BUILD_LOG=y",
        ]) + "\n")
    run("cd {} && make defconfig".format(SRC_DIR), shell=True)

    # 4. Build kernel only
    step("Compiling kernel — this takes 1-3 hours on first run ...")
    step("You can leave this running; the kernel is cached afterwards.")
    r = run("cd {} && make -j$(nproc) target/linux/compile".format(SRC_DIR),
            shell=True)
    if r.returncode != 0:
        fail("Kernel compile failed. Check output above.")

    if not os.path.exists(vmlinux):
        # Try alternate path
        for root, dirs, files in os.walk(os.path.join(SRC_DIR, "build_dir")):
            if "vmlinux" in files:
                vmlinux = os.path.join(root, "vmlinux")
                break

    if not os.path.exists(vmlinux):
        fail("vmlinux not found after build.")

    ok("Patched kernel built: " + vmlinux)
    return vmlinux


# ---------------------------------------------------------------------------
# Firmware assembly
# ---------------------------------------------------------------------------

def buildCustomPineappleImage(target, mode):
    step("Building firmware for {} ({} mode) ...".format(target, mode.upper()))

    # FULL mode: build the patched kernel first
    kernel = None
    if mode == "full":
        kernel = buildPatchedKernel()

    pkgs = (
        "at autossh base-files bash blockd block-mount busybox "
        "ca-bundle ca-certificates coreutils coreutils-base64 "
        "coreutils-sleep curl dbus dnsmasq e2fsprogs ebtables ethtool "
        "file firewall fstools fwtool getrandom glib2 "
        "hostapd-common hostapd-utils ip6tables iptables "
        "iptables-mod-ipmark iptables-mod-ipopt iw iwinfo jshn "
        "jsonfilter kmod-bluetooth kmod-cfg80211 kmod-crypto-aead "
        "kmod-crypto-cmac kmod-crypto-crc32c kmod-crypto-ecb "
        "kmod-crypto-ecdh kmod-crypto-hash kmod-crypto-kpp "
        "kmod-crypto-manager kmod-crypto-null kmod-crypto-pcompress "
        "kmod-ebtables kmod-fs-autofs4 kmod-fs-ext4 kmod-fs-ntfs "
        "kmod-fs-vfat kmod-fuse kmod-gpio-button-hotplug kmod-hid "
        "kmod-i2c-core kmod-i2c-mt7628 kmod-input-core kmod-input-evdev "
        "kmod-ip6tables kmod-ipt-compat-xtables kmod-ipt-conntrack "
        "kmod-ipt-core kmod-ipt-ipmark kmod-ipt-ipopt kmod-ipt-nat "
        "kmod-ipt-offload kmod-leds-gpio kmod-lib-crc16 "
        "kmod-lib-crc-ccitt kmod-libphy kmod-mac80211 kmod-mii "
        "kmod-mmc kmod-mt76 kmod-mt7601u kmod-mt7603 kmod-mt76-core "
        "kmod-mt76-usb kmod-mt76x02-common kmod-mt76x02-usb kmod-mt76x2 "
        "kmod-mt76x2-common kmod-mt76x2u kmod-nf-conntrack "
        "kmod-nf-conntrack6 kmod-nf-flow kmod-nf-ipt kmod-nf-ipt6 "
        "kmod-nf-nat kmod-nf-reject kmod-nf-reject6 kmod-nls-base "
        "kmod-nls-cp437 kmod-nls-iso8859-1 kmod-nls-utf8 kmod-ppp "
        "kmod-pppoe kmod-pppox kmod-regmap-core kmod-scsi-core "
        "kmod-sdhci kmod-sdhci-mt7620 kmod-slhc kmod-usb2 "
        "kmod-usb-acm kmod-usb-core kmod-usb-ehci kmod-usb-net "
        "kmod-usb-net-asix kmod-usb-net-asix-ax88179 "
        "kmod-usb-net-rtl8152 kmod-usb-ohci kmod-usb-storage "
        "libatomic1 libattr libblkid1 libblobmsg-json20210516 "
        "libbz2-1.0 libc libcbor0 libcomerr0 libcurl4 libdbus libelf1 "
        "libevdev libexpat libext2fs2 libffi libfido2-1 libgcc1 "
        "libgmp10 libgnutls libical libip4tc2 libip6tc2 "
        "libiwinfo20210430 libiwinfo-data libjson-c5 "
        "libjson-script20210516 liblzma libmagic libmbedtls12 "
        "libncurses6 libnettle8 libnghttp2-14 libnl-core200 "
        "libnl-genl200 libnl-tiny1 libopenssl1.1 libopenssl-conf "
        "libpcap1 libpcre libpthread libpython3-3.9 libreadline8 "
        "librt libsqlite3-0 libss2 libstdcpp6 libubox20210516 "
        "libubus20210630 libuci20130104 libuclient20201210 "
        "libudev-zero libusb-1.0-0 libustream-openssl20201210 "
        "libuuid1 libxtables12 logd macchanger msmtp "
        "mt7601u-firmware mtd nano netifd ntfs-3g odhcp6c "
        "odhcpd-ipv6only openssh-client openssh-client-utils "
        "openssh-keygen openssh-server openssh-sftp-server "
        "openssl-util openwrt-keyring opkg ppp ppp-mod-pppoe "
        "procd procps-ng procps-ng-free procps-ng-kill "
        "procps-ng-pgrep procps-ng-pkill procps-ng-ps "
        "procps-ng-snice procps-ng-top procps-ng-uptime "
        "procps-ng-watch protobuf-lite python3-base python3-codecs "
        "python3-email python3-light python3-logging python3-openssl "
        "python3-urllib swconfig tcpdump terminfo ubox ubus "
        "ubusd uci uclibcxx uclient-fetch urandom-seed urngd "
        "usbids usbutils usign vim wireless-regdb wireless-tools "
        "wpad zlib "
        "-libustream-wolfssl -libustream-wolfssl20201210 "
        "-wpad-basic -wpad-basic-wolfssl -wpad-basic-mbedtls "
        "-wpad-wolfssl -wpad-mbedtls"
    )

    # FILES must point at the overlay directory itself
    kernel_arg = 'KERNEL="{}" '.format(kernel) if kernel else ""

    cmd = ('make -C "{ib}" image PROFILE={prof} {k}'
           'PACKAGES="{pkgs}" FILES="{ovl}/"').format(
                ib=IB_DIR, prof=PROFILE, k=kernel_arg,
                pkgs=pkgs, ovl=OVERLAY_DIR)
    cprint("[+] " + cmd, 'cyan')
    r = run(cmd)
    if r.returncode != 0:
        fail("make failed with code {}".format(r.returncode))
    ok("Firmware compiled.")


def collectOutput(target):
    step("Collecting output ...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    src = os.path.join(IB_DIR, "bin", "targets", "ramips", "mt76x8")
    if not os.path.isdir(src):
        fail("Image directory missing: " + src)
    for f in os.listdir(src):
        if f.endswith(".bin") or f.endswith(".manifest") or f == "sha256sums":
            run('cp -a {} {}'.format(os.path.join(src, f), OUTPUT_DIR), shell=True)
    ok("Firmware in " + OUTPUT_DIR)
    for f in sorted(os.listdir(OUTPUT_DIR)):
        cprint("    {:<70} {} bytes".format(
            f, os.path.getsize(os.path.join(OUTPUT_DIR, f))), 'white')


def cleaning(target, mode):
    step("Cleaning intermediate files ...")
    # Keep the source tree in FULL mode so the kernel cache survives
    to_remove = [IB_TARBALL, EXTRACT_DIR, IB_DIR]
    for p in to_remove:
        if os.path.isdir(p):
            run('rm -rf ' + p, shell=True)
        elif os.path.isfile(p):
            os.remove(p)

    cprint("\n[INFO] Custom firmware: " + OUTPUT_DIR, 'cyan', attrs=['bold'])
    cprint("[INFO] Mode: {}".format(mode.upper()), 'cyan', attrs=['bold'])
    if mode == "full":
        cprint("[INFO] Kernel cache: " + SRC_DIR, 'cyan', attrs=['bold'])
        cprint("       (delete to force a kernel rebuild)", 'cyan')
    cprint("[INFO] Flash on {} via Breed — firmware layout.".format(target),
           'cyan', attrs=['bold'])
    cprint("[WARN] Back up Breed eeprom.bin before flashing!",
           'yellow', attrs=['bold'])


# ---------------------------------------------------------------------------
# Auto-launch the runner
# ---------------------------------------------------------------------------

def auto_run_in_qemu():
    if not os.path.exists(RUNNER_PY):
        warn("mk7-runner.py not found — skipping auto-launch.")
        cprint("    Place mk7-runner.py in {} to enable auto-run."
               .format(SCRIPT_DIR), 'cyan')
        return

    if not os.access(RUNNER_PY, os.X_OK):
        try:
            os.chmod(RUNNER_PY, 0o755)
        except Exception as e:
            warn("Cannot chmod +x runner: {}".format(e))

    print()
    cprint("=" * 68, 'green', attrs=['bold'])
    cprint("  Build complete — launching firmware in QEMU now",
           'green', attrs=['bold'])
    cprint("=" * 68, 'green', attrs=['bold'])
    print()
    cprint("  Ctrl-C within 3 seconds to skip.", 'yellow')
    for i in range(3, 0, -1):
        sys.stdout.write("\r  Starting in {} ...".format(i))
        sys.stdout.flush()
        time.sleep(1)
    print("\r  Starting now.          ")

    try:
        os.execv(sys.executable, [sys.executable, RUNNER_PY])
    except Exception as e:
        warn("Could not auto-launch runner: {}".format(e))
        cprint("    Run manually: sudo python3 " + RUNNER_PY, 'cyan')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    banner()
    cprint("[+] Hi there, let's cook a nice and tasty pineapple cake!\n",
           'green', attrs=['bold'])
    time.sleep(1)

    try:
        mode = selectBuildMode()
        cprint("[OK] Mode: {}".format(mode.upper()),
               'green', attrs=['bold'])

        answer = selectTarget()
        target = answer['target']
        cprint("[OK] Target: {}".format(target),
               'green', attrs=['bold'])

        checkDependencies(mode)
        downloadPineappleFw()
        unpackPineappleFw()
        extractPineappleOverlay()
        applyPortabilityPatches()
        downloadOpenwrtImageBuilder()
        extractOpenwrtImageBuilder()
        patchPrereqBuild()
        buildCustomPineappleImage(target, mode)
        collectOutput(target)
        cleaning(target, mode)
        auto_run_in_qemu()

    except SystemExit:
        raise
    except KeyboardInterrupt:
        print('\n[!] Interrupted.\n')
        sys.exit(1)
    except Exception as e:
        print('\n[!] See you soon for a new adventure!\n')
        print("    " + str(e) + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()