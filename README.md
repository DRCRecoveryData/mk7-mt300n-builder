# Sweet Pineapple Builder — MK7 Edition

Port **WiFi Pineapple Mark VII 2.1.3-stable** firmware to single-radio
MediaTek MT7628 routers — GL.iNet MT300N-V2, MT300N-V2 Mini, and
compatible boards with a 32 MB flash chip.

This is the Mark VII counterpart to *Sweet Pineapple Builder* for the
Tetra. It extracts the Pineapple userspace from the official Hak5
image, applies five portability patches, and recompiles a clean
firmware with the OpenWrt 21.02.1 Image Builder.

> **FOR EDUCATIONAL PURPOSE ONLY.**

---

## What the script does

1. Verifies host dependencies (`binwalk`, `sasquatch`, `wget`, `gawk`, …)
2. Downloads `upgrade-2.1.3-stable.2022101708401.bin` (~24 MB)
3. Verifies its SHA-256: `d8cae7ab5efa390b272f14d69c27a556b4689a47b339783e13cced73c6d1a444`
4. Extracts the SquashFS rootfs
5. Copies the Pineapple overlay (UI, binaries, Python modules, libwifi)
6. Applies the portability patches
7. Downloads OpenWrt Image Builder for `ramips/mt76x8` (21.02.1)
8. Patches `prereq-build.mk` for Python 3.12+
9. Compiles the firmware for `hak5_wifi-pineapple-mk7`
10. Collects output into `./customFW/`

## The five portability patches

| # | File | Change | Reason |
|---|------|--------|--------|
| 1 | `/sbin/uci` | Wrapper that auto-creates `wireless.radioN` sections on `uci set` | Single-radio boards fail the wizard's hardcoded `radio1` write |
| 2 | `/etc/config/wireless` | Default config with `radio1` stub (`disabled=1`) | Gives the wizard a valid target before boot |
| 3 | `/etc/rc.local` | Removes the `mmcblk0` eMMC sanity check | MT300N-V2 has no eMMC |
| 4 | `/etc/pineapple.rc` | Comments out `usb on` | MK7-only binary |
| 5 | `/etc/uci-defaults/93-pineap.sh` | `wlan1mon` → `wlan0mon` | Only `wlan0` exists on MT300N-V2 |

Plus the `root` password is reset to `root` in the overlay's `/etc/shadow`.

## Requirements

### Host (Linux)

- Python 3.6+
- `binwalk` — `sudo apt install binwalk`
- `sasquatch` — **must be built from source**, see below
- `wget`, `gawk`, `git`, `tar`, `make`, `gcc`, `openssl`
- `python3-termcolor` — `sudo apt install python3-termcolor`
- ~5 GB free disk

### Target hardware

- **GL.iNet MT300N-V2** (or compatible MT7628 board)
- **32 MB flash chip** — the 16 MB stock chip is too small
- **Breed bootloader** already flashed
- **USB flash drive (8 GB+)** for extroot — mandatory, see below

## Quick start

```bash
chmod +x mk7-mt300n-builder.py
sudo ./mk7-mt300n-builder.py
```

You will be prompted to select a target (default: `mt300n-v2`).

Output image lands in `./customFW/`:

```
customFW/
├── openwrt-21.02.1-ramips-mt76x8-hak5_wifi-pineapple-mk7-squashfs-sysupgrade.bin
├── openwrt-21.02.1-ramips-mt76x8-hak5_wifi-pineapple-mk7.manifest
└── sha256sums
```

## Host setup — installing sasquatch

`sasquatch` is a patched `unsquashfs` that handles xz-compressed
SquashFS 4.0 — required to unpack the MK7 rootfs. It is not packaged
by any major distro.

```bash
git clone https://github.com/devttys0/sasquatch.git
cd sasquatch

# Modern C compilers reject the old signal-handler signatures
sed -i 's/^void sigwinch_handler()/void sigwinch_handler(int s)/' \
    squashfs4.3/squashfs-tools/unsquashfs.c 2>/dev/null || true
sed -i 's/^void sigalrm_handler()/void sigalrm_handler(int s)/' \
    squashfs4.3/squashfs-tools/unsquashfs.c 2>/dev/null || true

./build.sh
sudo cp src/sasquatch /usr/local/bin/
sasquatch -h
```

If `./build.sh` fails before extracting `squashfs4.3/`, run it once,
apply the `sed` fixes above to
`squashfs4.3/squashfs-tools/unsquashfs.c`, then:

```bash
cd squashfs4.3/squashfs-tools
make -j$(nproc)
sudo cp sasquatch /usr/local/bin/
```

## Flashing the MT300N-V2

### ⚠️ Back up Breed EEPROM first

The EEPROM region holds your radio calibration. Lose it and the Wi-Fi
is bricked permanently.

1. Power off the MT300N-V2
2. Hold the reset button
3. Apply USB power while holding reset
4. Release after ~4 seconds — Breed boots
5. Browse to `http://192.168.1.1`
6. **Firmware Backup** → save both:
   - `eeprom.bin` (~64 KB)
   - `fullflash.bin` (~32 MB)
7. Verify both files are non-zero on your PC

### Flash

1. Still in Breed, click **Firmware Update**
2. Choose the `…sysupgrade.bin` from `./customFW/`
3. Layout: **firmware** (not bootloader, not EEPROM, not full)
4. Upload — Breed reboots on completion

### First boot

1. Set your PC's Ethernet to static IP `172.16.42.42/24`
2. Plug into the LAN port
3. Wait **4–5 minutes** — Python `compileall` is slow on MT7628
4. SSH: `ssh root@172.16.42.1` — password `root`
5. Browser: `http://172.16.42.1:1471` — the Mark VII setup wizard

> **Do NOT flash the Hak5 recovery image (`mk7_recovery_1.0.1.bin`) on
> the MT300N-V2.** It exists to partition the Mark VII's eMMC and has
> no role here. Breed is your recovery mechanism.

## USB drive / extroot — required

The MT300N-V2's internal flash is too small for the full Pineapple
experience. Set up extroot so `/overlay` lives on a USB drive.

```bash
# On the MT300N-V2
opkg update
opkg install block-mount kmod-usb-storage kmod-fs-ext4 e2fsprogs
```

Format the USB drive as **ext4**, insert it, then follow the official
OpenWrt guide:
<https://openwrt.org/docs/guide-user/additional-software/extroot_configuration>

Once extroot is active:

- All modules, handshakes, logs, and reports persist on the USB stick
- Removing the drive reverts the device to the internal overlay

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `No module named 'termcolor'` | Missing dep | `sudo apt install python3-termcolor` |
| `No such file or directory: 'cake/mk7fw.bin'` | `cake/` not writable | `sudo mkdir -p cake && sudo chmod 777 cake` |
| `sasquatch NOT FOUND` | Not installed | Build from source (see above) |
| `binwalk` fails to extract rootfs | Missing `sasquatch` | Same |
| `prereq-build` fails | Python 3.12+ | Script auto-patches; re-run |
| `make: *** No rule to make target` | Wrong Image Builder | Delete `cake/openwrt-imagebuilder-*` and re-run |
| First boot: red LED, stalls | Old build without `rc.local` patch | Rebuild with this script |
| Wizard dies on `radio1` | `uci` wrapper not in image | Verify `/sbin/uci` and `/sbin/uci.real` exist |
| No Wi-Fi after flash | EEPROM clobbered | Restore `eeprom.bin` via Breed |
| UI loads, no radios | Interface name mismatch | `uci set pineap.@config[0].pineap_interface='wlan0mon'; uci commit pineap` |

### Verifying the image offline

You can confirm the userspace works before flashing by booting the
extracted rootfs under QEMU:

```bash
sudo apt install -y qemu-user-static binfmt-support
sudo mkdir -p /tmp/mk7chroot
sudo cp -a cake/_mk7fw.bin.extracted/squashfs-root/. /tmp/mk7chroot/
sudo mount -t proc /proc /tmp/mk7chroot/proc
sudo mount --bind /dev /tmp/mk7chroot/dev
sudo chroot /tmp/mk7chroot /bin/sh
```

Inside the chroot, create `/tmp/board.json` and
`/etc/config/{system,network}`, run the UCI defaults, then launch
`/pineapple/pineapple`. `curl http://127.0.0.1:1471/` should return the
Pineapple login page.

## Credits

- **Hak5** for the WiFi Pineapple platform
- **OpenWrt** for the `ramips/mt76x8` target
- **Naqwada / Necrum Security Labs** for the *Sweet Pineapple Builder*
  concept and this script's structure
- **devttys0** for `sasquatch`
- **SHUR1K-N** for the Mangoapple resources that inspired the
  portability fixes

## License

MIT.
