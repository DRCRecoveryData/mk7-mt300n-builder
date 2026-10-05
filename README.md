# Mark VII Portability Builder

Build WiFi Pineapple Mark VII firmware that runs on **single-radio
MediaTek MT7628 routers** — GL.iNet MT300N-V2, MT300N-V2 Mini, and
similar boards with only a 2.4 GHz radio.

This is the Mark VII equivalent of the *Sweet Pineapple Builder*
project for the Tetra. Instead of a one-size-fits-all router list, it
builds for the **`hak5_wifi-pineapple-mk7`** OpenWrt profile and adds
the userspace patches required to make MK7 firmware work on hardware
Hak5 never targeted.

> **FOR EDUCATIONAL PURPOSE ONLY.**

---

## Why a custom build?

The Mark VII firmware runs on **MIPS 24KEc (MT7628)**. So does the
MT300N-V2. But the official firmware assumes two radios
(`radio0` 2.4 GHz + `radio1` 5 GHz), an eMMC chip, MK7-specific GPIOs,
and a `usb` helper binary. Flash it to a single-radio, eMMC-less
router and the setup wizard dies at the first `uci set
wireless.radio1.country` call.

This builder takes the official MK7 rootfs, extracts the Pineapple
userspace, applies five hardware-portability patches, and assembles a
clean image with the OpenWrt Image Builder.

## Patches applied

| # | File | Change | Reason |
|---|------|--------|--------|
| 1 | `/etc/rc.local` | Remove `mmcblk0` eMMC sanity check | MT300N-V2 has no eMMC |
| 2 | `/etc/pineapple.rc` | Comment out `usb on` | MK7-only binary |
| 3 | `/sbin/uci` | Wrap `uci` to auto-create missing `wireless.radioN` sections | Single-radio boards |
| 4 | `/etc/config/wireless` | Pre-populate `radio1` as `disabled=1` | Gives the wizard a valid target |
| 5 | `/etc/uci-defaults/93-pineap.sh` | `wlan1mon` → `wlan0mon` | MT300N-V2 has only `wlan0` |

## What's inside the overlay

Copied verbatim from the official MK7 2.1.3-stable firmware:

- `/pineapple/` — the 9.6 MB Go web server and Angular UI
- `/usr/lib/pineapple/` — Python module tree (`modules`, `jobs`, `apikey`, …)
- `/usr/lib/libwifi.so*` — Wi-Fi helper library
- `/etc/pineapple/`, `/etc/pineape/` — config and cert templates
- Init scripts: `pineapd`, `pineapple`, `cc-client`, `resetssids`,
  `autossh`, `atd`
- Binaries: `pineap`, `pineapd`, `cc-client`, `C2*`, `aircrack-ng`,
  `aireplay-ng`, `airodump-ng`, `airmon-ng`
- UCI defaults: `90-firewall.sh`, `92-system.sh`, `93-pineap.sh`,
  `95-network.sh`, `97-pineapple.sh`

## Requirements

### Host (Linux)

- `binwalk`
- `sasquatch` — **must be built from source**; not in distro repos
- `wget`, `gawk`, `git`, `tar`, `make`, `gcc`, `python3`, `openssl`
- ~5 GB free disk
- Any recent Linux (tested on Ubuntu 22.04+, Debian 12+)

Install base deps:

```bash
sudo apt install -y binwalk wget gawk git build-essential python3 openssl
```

Build `sasquatch` (needed to unpack the MK7's SquashFS-with-xz):

```bash
git clone https://github.com/devttys0/sasquatch.git
cd sasquatch
# Fix signal-handler signatures for modern C compilers
sed -i 's/^void sigwinch_handler()/void sigwinch_handler(int s)/' \
    squashfs4.3/squashfs-tools/unsquashfs.c 2>/dev/null || true
./build.sh
sudo cp src/sasquatch /usr/local/bin/
```

If `./build.sh` fails before extracting `squashfs4.3/`, just run it once,
apply the sed, then run `make` inside `squashfs4.3/squashfs-tools`.

### Python

The script uses only the standard library — no `pip` install needed.

### Target hardware

- **GL.iNet MT300N-V2** with 32 MB flash chip (the 16 MB stock chip is too small)
- **Breed bootloader** already flashed to the chip
- A **USB flash drive** (8 GB+) for extroot — mandatory, see below
- (Optional) USB hub if you want the drive *and* a USB Wi-Fi adapter

## Quick start

```bash
chmod +x mk7-mt300n-builder.py
./mk7-mt300n-builder.py
```

The script will:

1. Verify host dependencies
2. Download `upgrade-2.1.3-stable.2022101708401.bin` (~24 MB)
3. Verify SHA-256
4. Extract with `binwalk` + `sasquatch`
5. Build the overlay (apply the 5 patches)
6. Download OpenWrt 21.02.1 Image Builder (`ramips/mt76x8`)
7. Patch `prereq-build.mk` for Python 3.12+
8. Compile the firmware for `hak5_wifi-pineapple-mk7`
9. Write the result to `./output/`

Output:

```
output/
├── openwrt-21.02.1-ramips-mt76x8-hak5_wifi-pineapple-mk7-squashfs-sysupgrade.bin
├── openwrt-21.02.1-ramips-mt76x8-hak5_wifi-pineapple-mk7.manifest
└── sha256sums
```

## Flashing the MT300N-V2

### ⚠️ Before anything: back up Breed EEPROM

The EEPROM region holds your Wi-Fi calibration data. If it is
overwritten and you don't have a backup, the radio is bricked.

1. Power off the MT300N-V2.
2. Hold the reset button.
3. Apply USB power while holding reset.
4. Release after ~4 seconds — the LED enters Breed mode.
5. On your PC, browse to `http://192.168.1.1`.
6. **Firmware Backup** → save both:
   - `eeprom.bin` (~64 KB)
   - `fullflash.bin` (~32 MB)
7. Verify both files are non-zero on your PC.

### Flash the firmware

1. Still in Breed, click **Firmware Update**.
2. Choose the `...sysupgrade.bin` from `./output/`.
3. Flash layout: **firmware** (not bootloader, not EEPROM, not full).
4. Upload — Breed reboots on completion.

### First boot

1. Set your PC's Ethernet to static IP `172.16.42.42/24`.
2. Plug into the MT300N-V2 LAN port.
3. Wait 4–5 minutes (Python `compileall` is slow on MT7628).
4. SSH: `ssh root@172.16.42.1` — password `root`.
5. Browse to `http://172.16.42.1:1471`. The MK7 setup wizard runs.

> **Do NOT flash the Hak5 recovery image (`mk7_recovery_1.0.1.bin`)
> on the MT300N-V2.** It exists to partition the Mark VII's eMMC and
> has no role on the MT300N-V2. Breed is your recovery mechanism.

## USB drive / extroot — required

The MT300N-V2's internal flash is too small for the full Pineapple
experience. Set up extroot on a USB drive so `/overlay` lives on
external storage.

```bash
# On the MT300N-V2
opkg update
opkg install block-mount kmod-usb-storage kmod-fs-ext4 e2fsprogs
```

Format the USB drive as **ext4**, insert it, then follow the official
OpenWrt guide: <https://openwrt.org/docs/guide-user/additional-software/extroot_configuration>

Once extroot is active, all modules, handshakes, logs, and reports
persist on the USB stick. Removing the stick reverts the device to the
internal overlay.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Build fails on `prereq-build` | Python 3.12+ missing `distutils` | Script patches this; re-run |
| `binwalk` cannot extract rootfs | `sasquatch` missing | Build it (see Requirements) |
| `uci: Entry not found` on `radio1` | Wrapper not copied | Confirm `/sbin/uci` and `/sbin/uci.real` exist in the image |
| First boot stalls with red LED | Old build without rc.local patch | Re-flash the latest output |
| No Wi-Fi after flash | EEPROM clobbered | Restore `eeprom.bin` via Breed |
| UI loads, no radios | Interface name mismatch | `uci set pineap.@config[0].pineap_interface='wlan0mon'; uci commit pineap` |

## Verifying the image offline (optional)

You can boot the extracted rootfs in a QEMU chroot to confirm the
userspace works before flashing:

```bash
sudo apt install -y qemu-user-static binfmt-support
sudo mkdir -p /tmp/mk7chroot
sudo cp -a ./cake/_mk7_fw.bin.extracted/squashfs-root/. /tmp/mk7chroot/
sudo mount -t proc /proc /tmp/mk7chroot/proc
sudo mount --bind /dev /tmp/mk7chroot/dev
sudo chroot /tmp/mk7chroot /bin/sh
```

Inside: create `/tmp/board.json` and `/etc/config/{system,network}`,
run the UCI defaults, start `/pineapple/pineapple`, and `curl
http://127.0.0.1:1471/`. You should see the Pineapple login page.

## Credits

- **Hak5** for the WiFi Pineapple platform
- **OpenWrt** for the ramips/mt76x8 target
- **Naqwada / Necrum Security Labs** for the *Sweet Pineapple Builder*
  concept and this script's structure
- **devttys0** for `sasquatch`
- **SHUR1K-N** for the Mangoapple resources that inspired the
  portability fixes

## License

MIT — see `LICENSE`.
