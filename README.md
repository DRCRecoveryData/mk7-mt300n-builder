# MK7 Portability Builder

Build **WiFi Pineapple Mark VII 2.1.3-stable** firmware for single-radio
MediaTek MT7628 routers — GL.iNet MT300N-V2, MT300N-V2 Mini, and
compatible boards with a 32 MB flash chip.

> **FOR EDUCATIONAL PURPOSE ONLY.**
>
> Flashing custom firmware voids warranties and can brick your device.
> Breed bootloader is your safety net — back up the EEPROM before flashing.

---

## What This Is

The Mark VII runs on **MediaTek MT7628 (MIPS 24KEc)**. So does the
MT300N-V2. But the official MK7 firmware assumes:
- Two radios (`radio0` 2.4 GHz + `radio1` 5 GHz)
- An eMMC chip for storage
- MK7-specific GPIOs for reset button and LEDs
- A `usb` helper binary that only exists on the MK7

Flash the stock firmware on a single-radio, eMMC-less router and the
setup wizard dies at the first `uci set wireless.radio1.country` call.

This project extracts the Pineapple userspace from the official MK7
image, applies portability patches, and reassembles a firmware that
boots on the MT300N-V2.

Two build modes:

| Mode | Time | Reset Button | LEDs | Use Case |
| :--- | :--- | :--- | :--- | :--- |
| **QUICK** | ~5 min | ❌ Broken (use SSH) | ⚠️ Cosmetic | Fast iteration |
| **FULL** | 1–3 h first run | ✅ Works | ✅ Works | Final firmware |

---

## Repository Contents

| File | Purpose |
| :--- | :--- |
| `mk7-mt300n-builder.py` | Builds the firmware. Two modes: QUICK (Image Builder) or FULL (patched kernel). |
| `mk7-runner.py` | Boots the built firmware in QEMU, bypasses the setup wizard, opens the dashboard in Firefox. |
| `README.md` | This file. |

---

## Requirements

### Host (Linux)

- Python 3.6+
- `binwalk`
- `sasquatch` — **must be built from source**, not in distro repos
- `wget`, `gawk`, `git`, `tar`, `make`, `gcc`, `openssl`
- `python3-termcolor` — `sudo apt install python3-termcolor`
- For FULL mode: `rsync`, `unzip`, `python3-distutils` (or the modern equivalent)
- ~5 GB free disk (QUICK) / ~8 GB (FULL)
- Any recent Linux — tested on Ubuntu 22.04+

### Installing dependencies

```bash
sudo apt install -y \
    binwalk wget gawk git build-essential python3 \
    python3-termcolor openssl rsync unzip
```

### Building sasquatch

`sasquatch` is a patched `unsquashfs` that handles xz-compressed
SquashFS 4.0 — required to unpack the MK7 rootfs.

```bash
git clone https://github.com/devttys0/sasquatch.git
cd sasquatch

# Modern compilers reject the old signal handler signatures
sed -i 's/^void sigwinch_handler()/void sigwinch_handler(int s)/' \
    squashfs4.3/squashfs-tools/unsquashfs.c 2>/dev/null || true
sed -i 's/^void sigalrm_handler()/void sigalrm_handler(int s)/' \
    squashfs4.3/squashfs-tools/unsquashfs.c 2>/dev/null || true

./build.sh
sudo cp src/sasquatch /usr/local/bin/
sasquatch -h    # should print a banner
```

### QEMU (for the runner)

```bash
sudo apt install -y qemu-user-static binfmt-support
sudo update-binfmts --enable qemu-mipsel
ls /proc/sys/fs/binfmt_misc/qemu-mipsel   # should exist
```

---

## Quick Start

### One command — build + run

```bash
cd ~/Desktop
chmod +x mk7-mt300n-builder.py mk7-runner.py
sudo ./mk7-mt300n-builder.py
```

You will be prompted for:

1. **Build mode** — `[1] QUICK` or `[2] FULL`
2. **Target** — `[1] mt300n-v2`, `[2] mt300n-v2-mini`, `[3] generic-mt7628`

The builder then:

1. Downloads MK7 firmware (~24 MB)
2. Verifies SHA-256
3. Extracts rootfs with binwalk + sasquatch
4. Copies Pineapple userspace into `cake/overlay/`
5. Applies portability patches
6. (FULL mode) Clones OpenWrt, patches DTS, compiles kernel
7. Downloads Image Builder (~46 MB)
8. Compiles firmware
9. Writes to `~/Desktop/customFW/`
10. **Auto-launches `mk7-runner.py`** → Firefox opens the dashboard

---

## Patches Applied

| # | File | Change | Reason |
| :--- | :--- | :--- | :--- |
| 1 | `/sbin/uci` | Wrapper that auto-creates `wireless.radioN` sections on `uci set` | Single-radio boards fail the wizard's hardcoded `radio1` write |
| 2 | `/etc/config/wireless` | Pre-populate `radio1` as `disabled=1` | Gives the wizard a valid target |
| 3 | `/etc/rc.local` | Remove `mmcblk0` eMMC sanity check | MT300N-V2 has no eMMC |
| 4 | `/etc/pineapple.rc` | Comment out `usb on` | MK7-only binary |
| 5 | `/etc/uci-defaults/93-pineap.sh` | `wlan1mon` → `wlan0mon` | Only `wlan0` exists on MT300N-V2 |
| 6 | `/etc/shadow` | Set root password to `root` | For SSH access during setup |

**FULL mode additionally patches** the kernel DTS:

| Node | MK7 Value | MT300N-V2 Value |
| :--- | :--- | :--- |
| `keys → reset → gpios` | `&gpio 11` | `&gpio 38` |
| `leds → led_blue` | `&gpio 3` | `&gpio 42` |
| `leds → led_green` | `&gpio 2` | `&gpio 43` |
| `leds → led_red` | `&gpio 0` | `&gpio 44` |

---

## Output

```
~/Desktop/customFW/
├── openwrt-21.02.1-ramips-mt76x8-hak5_wifi-pineapple-mk7-squashfs-sysupgrade.bin
├── openwrt-21.02.1-ramips-mt76x8-hak5_wifi-pineapple-mk7.manifest
└── sha256sums
```

The `.bin` is ~23 MB, valid u-boot uImage, flashable via Breed as
**firmware** layout.

---

## Flashing the MT300N-V2

### ⚠️ Back up Breed EEPROM first

The EEPROM region holds your radio calibration. Lose it and Wi-Fi is
bricked permanently.

1. Power off the MT300N-V2
2. Hold the reset button
3. Apply USB power while holding reset
4. Release after ~4 seconds — Breed boots
5. Browse to `http://192.168.1.1`
6. **Firmware Backup** → save both:
   - `eeprom.bin` (~64 KB) — critical
   - `fullflash.bin` (~32 MB)
7. Verify both files are non-zero on your PC

### Flash

1. Still in Breed, click **Firmware Update**
2. Choose `customFW/*-sysupgrade.bin`
3. Layout: **firmware** (not bootloader, not EEPROM, not full)
4. Upload — Breed reboots on completion

### First boot

1. Set your PC's Ethernet to static IP `172.16.42.42/24`
2. Plug into the LAN port
3. Wait **4–5 minutes** — Python `compileall` is slow on MT7628
4. SSH: `ssh root@172.16.42.1` (password `root`)
5. Browser: `http://172.16.42.1:1471`

**In QUICK mode:**
The wizard appears. Click **"Continue with Radios Disabled"** to
proceed without the reset button. If the final step fails, bypass it
over SSH:

```bash
ssh root@172.16.42.1
rm -f /etc/pineapple/setup_required
touch /etc/pineapple/allow_admin_all
/etc/init.d/pineapple restart
```

**In FULL mode:**
The reset button works. Press it when the wizard says "Hold for 4
Seconds". Wizard completes normally.

> **Do NOT flash the Hak5 recovery image (`mk7_recovery_1.0.1.bin`) on
> the MT300N-V2.** It exists to partition the MK7's eMMC. Breed is your
> recovery mechanism.

---

## USB Drive / Extroot — Required

The MT300N-V2's internal flash is too small for the full Pineapple
experience. Set up extroot so `/overlay` lives on a USB drive.

```bash
# On the MT300N-V2
opkg update
opkg install block-mount kmod-usb-storage kmod-fs-ext4 e2fsprogs
```

Format the USB drive as **ext4**, insert, and follow:
<https://openwrt.org/docs/guide-user/additional-software/extroot_configuration>

Once active:
- All modules, handshakes, logs, reports persist on the USB stick
- Removing the drive reverts the device to the internal overlay

---

## Preview in QEMU (No Hardware Required)

The builder automatically hands off to `mk7-runner.py`, which:

1. Extracts the built `.bin`
2. Builds a chroot at `/tmp/mk7chroot`
3. Fixes binwalk's symlink rewrites
4. Stages `board.json` and UCI configs
5. **Two-phase wizard bypass** — launches Pineapple, kills it, removes
   `setup_required`, relaunches
6. Waits for port 1471
7. **Launches Firefox via `systemd-run --user`** — opens the dashboard

### Runner invocation

```bash
sudo ./mk7-runner.py
```

### Interactive controls

Once running:

| Key | Action |
| :--- | :--- |
| **Enter** | Stop Pineapple, unmount chroot, clean up |
| `c` | Re-open the dashboard in Firefox |
| `w` | Open the raw root URL in Firefox |
| `l` | Tail the Pineapple log |

### What QEMU Proves

| Layer | Verified |
| :--- | :--- |
| All MIPS binaries load | ✅ |
| Shared libraries resolve | ✅ |
| Python modules import | ✅ |
| Pineapple Go binary starts | ✅ |
| TCP 1471 binds | ✅ |
| Angular UI serves | ✅ |
| Setup wizard steps 1–4 render | ✅ |
| REST APIs respond | ✅ |
| Backend reaches `hostapd wlan0` apply step | ✅ (fails here only in QEMU — no radio) |

**What QEMU cannot test:** kernel boot on real hardware, MT7603E radio
init, native `pineapd`, GPIO behaviour. Those require an actual device.

---

## Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `No module named 'termcolor'` | Missing dep | `sudo apt install python3-termcolor` |
| `sasquatch NOT FOUND` | Not built | See "Building sasquatch" above |
| `binwalk` produces no rootfs | sasquatch missing | Same |
| `make` fails: `libustream-wolfssl` conflict | Package clash. | Builder excludes it automatically; if manual, add `-libustream-wolfssl` to `PACKAGES` |
| Build fails: `cp: cannot copy directory into itself` | Wrong `FILES=` path | Builder uses overlay dir itself; verify `FILES=` ends with `/overlay/` |
| `[x] No sysupgrade .bin found` | Path mismatch | Runner looks in `~/Desktop/customFW/`; verify the builder wrote there |
| Runner: `binwalk extraction uses many third party utilities` | Needs `--run-as=root` | Runner passes this flag |
| Firefox doesn't open in runner | Wayland + snap restrictions | Runner uses `systemd-run --user`; if still failing, run manually: `systemd-run --user --scope /snap/bin/firefox --new-window "http://1270.0.1:1471/#/Dashboard"` |
| Wizard shows `hostapd failed to set wlan0 client filter: exit status 255` | No radio in QEMU | Bypass via SSH (see below) or click "Continue with Radios Disabled" |
| Real hardware: wizard same error | Radio not initialised | Check `dmesg \| grep mt7603`; restore `eeprom.bin` via Breed |
| No Wi-Fi after flash | EEPROM clobbered | Restore `eeprom.bin` via Breed |
| First boot: red LED, stalls | Old build without `rc.local` patch | Rebuild with this script |

### Wizard bypass over SSH

If the wizard fails on real hardware:

```bash
ssh root@172.16.42.1
rm -f /etc/pineapple/setup_required
touch /etc/pineapple/allow_admin_all
/etc/init.d/firewall restart
/etc/init.d/pineapple restart
```

Then browse to `http://172.16.42.1:1471/#/Dashboard`.

### Firefox launch — manual fallback

If the runner can't launch Firefox:

```bash
systemd-run --user --scope --quiet /snap/bin/firefox \
  --new-window "http://127.0.0.1:1471/#/Dashboard"
```

---

## Hardware Limitations

The MT300N-V2 is not a Mark VII. Some things cannot work identically:

| Feature | MT300N-V2 Status | Workaround |
| :--- | :--- | :--- |
| **Radios** | 1× 2.4 GHz (MT7603E) | USB Wi-Fi adapter for PineAP monitor mode |
| **Storage** | 32 MB NOR only | USB drive + extroot |
| **Reset button (QUICK mode)** | Non-functional | SSH bypass |
| **Reset button (FULL mode)** | Functional | DTS patch applied |
| **LEDs (QUICK mode)** | Cosmetic only | Ignore |
| **LEDs (FULL mode)** | Functional | DTS patch applied |
| **5 GHz** | Not supported | USB adapter required |
| **Simultaneous AP + monitor** | Single radio cannot do both | USB adapter required |

### PineAP Functionality

For full PineAP (beacon flooding, deauth, client probing):

1. Internal `wlan0` handles the management AP
2. USB Wi-Fi adapter (Atheros AR9271, Ralink RT5370, or MediaTek
   MT7612U chipset) handles monitor mode + injection

```bash
# On the device, set PineAP to use the USB adapter
uci set pineap.@config[0].pineap_interface='wlan1mon'
uci commit pineap
/etc/init.d/pineapd restart
```

---

## Files Generated

| Path | Size | Contents |
| :--- | :--- | :--- |
| `~/Desktop/cake/` | ~500 MB | Working directory (deleted by builder except in FULL mode) |
| `~/Desktop/cake/openwrt-src/` | ~3 GB | OpenWrt source tree (FULL mode only, cached for rebuilds) |
| `~/Desktop/customFW/` | ~23 MB | **Final firmware** |
| `~/Desktop/pineapple-run.log` | small | Pineapple backend stdout during QEMU run |
| `/tmp/mk7chroot/` | ~70 MB | QEMU chroot (deleted on runner exit) |

### Cleaning up

```bash
sudo pkill -f mk7-runner
sudo pkill -f pineapple
sudo pkill -f qemu-mipsel
sudo umount -l /tmp/mk7chroot/proc 2>/dev/null
sudo umount -l /tmp/mk7chroot/sys  2>/dev/null
sudo umount -l /tmp/mk7chroot/dev/pts 2>/dev/null
sudo umount -l /tmp/mk7chroot/dev 2>/dev/null

cd ~/Desktop
sudo rm -rf cake customFW /tmp/mk7chroot pineapple-run.log
```

---

## Verification

### Verify the built firmware

```bash
cd ~/Desktop
ls -lh customFW/*.bin
file customFW/*.bin
hexdump -C customFW/*.bin | head -3
```

Expected:
- Size ~23 MB
- `u-boot legacy uImage, MIPS OpenWrt Linux-5.4.154`
- Magic bytes `27 05 19 08` (or similar uImage magic)

### SHA-256 of the MK7 source firmware

The builder verifies this automatically:

```
d8cae7ab5efa390b272f14d69c27a556b4689a47b339783e13cced73c6d1a444
```

---

## Credits

- **Hak5** for the WiFi Pineapple platform
- **OpenWrt** for the `ramips/mt76x8` target and Image Builder
- **Naqwada / Necrum Security Labs** for the Sweet Pineapple Builder
  concept
- **devttys0** for `sasquatch`
- **SHUR1K-N** for the Mangoapple resources that inspired the DTS
  portability approach

---

## License

MIT.

---

## Disclaimer

This project is for **educational and legitimate penetration testing
purposes only**. Only use it on networks and devices you own or have
explicit written permission to test. The authors are not responsible
for misuse, damage to hardware, or legal consequences.