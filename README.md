# MK7 Portability Builder

Build **WiFi Pineapple Mark VII 2.1.3-stable** firmware for single-radio
MediaTek MT7628 routers — GL.iNet MT300N-V2, MT300N-V2 Mini, and
compatible boards with a 32 MB flash chip.

> **FOR EDUCATIONAL PURPOSE ONLY.**
>
> Flashing custom firmware voids warranties and can brick your device.
> Breed bootloader is your safety net — back up the EEPROM before flashing.

---

## Table of Contents

1. [What This Is](#what-this-is)
2. [Repository Contents](#repository-contents)
3. [Requirements](#requirements)
4. [Quick Start](#quick-start)
5. [Patches Applied](#patches-applied)
6. [Output](#output)
7. [Flashing the MT300N-V2](#flashing-the-mt300n-v2)
8. [USB Drive / Extroot](#usb-drive--extroot)
9. [Preview in QEMU](#preview-in-qemu-no-hardware-required)
10. [Advanced: FULL Mode DTS Patch](#advanced-full-mode-dts-patch)
11. [Advanced: Real-Hardware Debugging](#advanced-real-hardware-debugging)
12. [Advanced: MT300N-V2 Board Revisions](#advanced-mt300n-v2-board-revisions)
13. [Advanced: Mangoapple Reference](#advanced-mangoapple-reference)
14. [Troubleshooting](#troubleshooting)
15. [Hardware Limitations](#hardware-limitations)
16. [Files Generated](#files-generated)
17. [Verification](#verification)
18. [Credits](#credits)
19. [License](#license)
20. [Disclaimer](#disclaimer)

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
- For FULL mode: `rsync`, `unzip`, `python3-distutils` (or modern equivalent)
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

### Userspace patches (both QUICK and FULL modes)

| # | File | Change | Reason |
| :--- | :--- | :--- | :--- |
| 1 | `/sbin/uci` | Wrapper that auto-creates `wireless.radioN` sections on `uci set` | Single-radio boards fail the wizard's hardcoded `radio1` write |
| 2 | `/etc/config/wireless` | Pre-populate `radio1` as `disabled=1` | Gives the wizard a valid target |
| 3 | `/etc/rc.local` | Remove `mmcblk0` eMMC sanity check | MT300N-V2 has no eMMC |
| 4 | `/etc/pineapple.rc` | Comment out `usb on` | MK7-only binary |
| 5 | `/etc/uci-defaults/93-pineap.sh` | `wlan1mon` → `wlan0mon` | Only `wlan0` exists on MT300N-V2 |
| 6 | `/etc/shadow` | Set root password to `root` | For SSH access during setup |

### Kernel DTS patches (FULL mode only)

The MK7 profile compiles a kernel with the **MK7's DTS** baked in — not
the MT300N-V2's. FULL mode patches these GPIO assignments:

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
   - `eeprom.bin` (~64 KB) — **critical**
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

## Advanced: FULL Mode DTS Patch

FULL mode patches the kernel's Device Tree Source (DTS) so the reset
button and LEDs work natively on the MT300N-V2. This section explains
how to verify the patch worked and how to fix it if it didn't.

### The DTS Patch Constants

At the top of `mk7-mt300n-builder.py`:

```python
MT300N_RESET_GPIO = 38      # reset button
MT300N_LED_BLUE   = 42      # power LED
MT300N_LED_GREEN  = 43      # WAN LED
MT300N_LED_RED    = 44      # WLAN LED
```

These values come from the GL.iNet MT300N-V2 mainline DTS in OpenWrt
v21.02.1. **They may differ on your board revision.**

### Verifying GPIO Numbers Before FULL Build

The reliable way: boot a stock OpenWrt image first, then check.

1. Flash stock OpenWrt for MT300N-V2 via Breed:
   ```
   https://downloads.openwrt.org/releases/21.02.1/targets/ramips/mt76x8/openwrt-21.02.1-ramips-mt76x8-glinet_gl-mt300n-v2-squashfs-sysupgrade.bin
   ```
2. SSH in: `ssh root@192.168.8.1`
3. Read GPIO map:
   ```bash
   cat /sys/kernel/debug/gpio
   ```
   Sample output:
   ```
   gpio-38  (                    |reset               ) in  hi
   gpio-42  (                    |blue:system         ) out lo
   gpio-43  (                    |green:system        ) out lo
   gpio-44  (                    |red:system          ) out lo
   ```
4. Note the numbers. If they differ from the defaults, edit
   `mk7-mt300n-builder.py` before running FULL mode.

### Detecting a Partial DTS Patch

If the DTS format in the source tree differs from what `sed` expects,
the script prints:

```
[!] DTS patch applied only 2 times — expected >= 4.
[!] Original DTS format may differ. Check: cake/openwrt-src/...
```

This means some GPIO overrides didn't apply. The firmware will still
build, but the affected hardware won't work.

**To fix:**

1. Open the DTS file:
   ```bash
   nano cake/openwrt-src/target/linux/ramips/dts/mt7628an_hak5_wifi-pineapple-mk7.dts
   ```
2. Find the `keys {` and `leds {` nodes
3. Edit `gpios = <&gpio X ...>` to match your board
4. Invalidate the kernel cache and rebuild:
   ```bash
   rm -rf cake/openwrt-src
   sudo ./mk7-mt300n-builder.py   # choose FULL mode again
   ```

### Forcing a Kernel Rebuild

The compiled kernel is cached at:

```
cake/openwrt-src/build_dir/target-mipsel_24kc_musl/linux-ramips_mt76x8/vmlinux
```

If you change the DTS or GPIO constants and want to force a rebuild:

```bash
rm -rf cake/openwrt-src
```

Then run FULL mode again. This triggers a fresh clone + compile
(1–3 hours the first time, but the toolchain cache in `cake/` may speed
up subsequent builds).

**Disk impact:** The full source tree + toolchain is ~3 GB. If you're
short on space, run `df -h ~/Desktop` before starting FULL mode.

---

## Advanced: Real-Hardware Debugging

If the flashed firmware doesn't boot or misbehaves on the MT300N-V2,
these tools help.

### Serial Console

The MT300N-V2 has UART pads on the PCB:

| Pad | Signal |
| :--- | :--- |
| `TX` | UART TX (from router) |
| `RX` | UART RX (to router) |
| `GND` | Ground |
| `VCC` | 3.3 V (do not connect to USB-TTL VCC) |

- Baud rate: **115200**
- Voltage: **3.3 V** (use a 3.3 V USB-TTL adapter — 5 V will damage the board)

Wiring:
```
USB-TTL GND → MT300N-V2 GND
USB-TTL RX  → MT300N-V2 TX
USB-TTL TX  → MT300N-V2 RX
USB-TTL 3V3 → (leave disconnected)
```

Terminal:
```bash
sudo screen /dev/ttyUSB0 115200
# or
sudo minicom -D /dev/ttyUSB0 -b 115200
```

You'll see the U-Boot banner, kernel messages, and init output. This
is the single most useful debug tool when the firmware hangs.

### Capturing Boot Log After SSH

If the router boots but services fail:

```bash
ssh root@172.16.42.1
dmesg | grep -iE "error|fail|mt76|mt7603|wlan"
logread | tail -100
cat /tmp/pp.out       # pineapple backend stdout
cat /tmp/pp.err       # pineapple backend stderr
```

### Verifying DTS Patch on Real Hardware

After flashing a FULL-mode image:

```bash
ssh root@172.16.42.1

# Check reset button GPIO
cat /sys/kernel/debug/gpio | grep -i reset
# Expected: gpio-38 ... |reset

# Check LEDs
cat /sys/kernel/debug/gpio | grep -iE "blue|green|red"
# Expected: gpio-42 (blue), gpio-43 (green), gpio-44 (red)

# Test the reset button — press it while running:
dmesg -w | grep -iE "gpio-keys|reset"
# Should print an event on press
```

If the GPIO assignments show different numbers than expected, the DTS
patch didn't take effect — re-verify and rebuild.

### Breed Recovery

If the firmware hangs and SSH doesn't work:

1. Power off the MT300N-V2
2. Hold the reset button
3. Apply USB power while holding reset
4. Release after ~4 seconds
5. Browse to `http://192.168.1.1`
6. Flash a different firmware, or restore `fullflash.bin`

Breed lives in a protected flash region that firmware writes cannot
overwrite. As long as you don't re-flash Breed itself, the device is
recoverable.

---

## Advanced: MT300N-V2 Board Revisions

There are at least two MT300N-V2 hardware revisions with different
GPIO assignments:

| Revision | Reset Button | Power LED | WAN LED | WLAN LED |
| :--- | :--- | :--- | :--- | :--- |
| **v1** | `gpio1 6` | `gpio1 10` | `gpio1 11` | `gpio1 12` |
| **v2** | `gpio 38` | `gpio 42` | `gpio 43` | `gpio 44` |

The script's defaults match **v2**. If you have a **v1** board:

1. Change the constants at the top of `mk7-mt300n-builder.py`:
   ```python
   MT300N_RESET_GPIO = 6    # v1
   MT300N_LED_BLUE   = 10
   MT300N_LED_GREEN  = 11
   MT300N_LED_RED    = 12
   ```
2. Adjust the `sed` patterns in `buildPatchedKernel()` to match the v1
   format (they may use `&gpio1` instead of `&gpio`)
3. Rebuild FULL mode

To determine your board revision:

```bash
# From a stock OpenWrt install:
cat /sys/firmware/devicetree/base/model
# "GL.iNet GL-MT300N-V2"  = generic
# or check the PCB silkscreen: "v1.0" / "v2.0"
```

---

## Advanced: Mangoapple Reference

The [WiFi Mangoapple project](https://github.com/SHUR1K-N/WiFi-Mangoapple-Resources)
by SHUR1K-N is a community effort that documents MT300N-V2 Pineapple
ports in detail. It contains:

- Pre-patched DTS files
- Verified GPIO numbers for various revisions
- Working configurations for OpenWrt v19.07 and v21.02
- Community-tested build recipes

Before spending hours on a FULL kernel build, check their repository —
they may already have the exact patch your board needs.

---

## Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `No module named 'termcolor'` | Missing dep | `sudo apt install python3-termcolor` |
| `sasquatch NOT FOUND` | Not built | See "Building sasquatch" above |
| `binwalk` produces no rootfs | sasquatch missing | Same |
| `make` fails: `libustream-wolfssl` conflict | Package clash | Builder excludes it automatically; if manual, add `-libustream-wolfssl` to `PACKAGES` |
| Build fails: `cp: cannot copy directory into itself` | Wrong `FILES=` path | Builder uses overlay dir itself; verify `FILES=` ends with `/overlay/` |
| `[x] No sysupgrade .bin found` | Path mismatch | Runner looks in `~/Desktop/customFW/`; verify the builder wrote there |
| Runner: `binwalk extraction uses many third party utilities` | Needs `--run-as=root` | Runner passes this flag |
| Firefox doesn't open in runner | Wayland + snap restrictions | Runner uses `systemd-run --user`; if still failing, run manually: `systemd-run --user --scope /snap/bin/firefox --new-window "http://127.0.0.1:1471/#/Dashboard"` |
| Wizard shows `hostapd failed to set wlan0 client filter: exit status 255` | No radio in QEMU | Bypass via SSH or click "Continue with Radios Disabled" |
| Real hardware: wizard same error | Radio not initialised | Check `dmesg \| grep mt7603`; restore `eeprom.bin` via Breed |
| No Wi-Fi after flash | EEPROM clobbered | Restore `eeprom.bin` via Breed |
| First boot: red LED, stalls | Old build without `rc.local` patch | Rebuild with this script |
| Partial DTS patch warning | DTS format differs | See "Detecting a Partial DTS Patch" above |
| Reset button doesn't work after FULL flash | Wrong GPIO for board revision | See "Board Revisions" above |

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
| `~/Desktop/cake/` | ~500 MB | Working directory |
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
- Magic bytes `27 05 19 56`

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