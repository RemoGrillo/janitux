<div align="center">

<img src="data/icons/hicolor/scalable/apps/io.github.RemoGrillo.Janitux.svg" width="112" alt="">

# Janitux

**Every full disk has a culprit. The janitor is on the case.**

[![Build](https://github.com/RemoGrillo/janitux/actions/workflows/build.yml/badge.svg)](https://github.com/RemoGrillo/janitux/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/RemoGrillo/janitux?color=3987e5)](https://github.com/RemoGrillo/janitux/releases/latest)
[![License: GPL v3+](https://img.shields.io/badge/license-GPL--3.0--or--later-1baf7a)](LICENSE)
<br>
[![Linux](https://img.shields.io/badge/platform-Linux-eda100?logo=linux&logoColor=black)](#install)
[![GTK 4](https://img.shields.io/badge/GTK-4.14%2B-4a86cf?logo=gtk&logoColor=white)](https://gtk.org)
[![libadwaita](https://img.shields.io/badge/libadwaita-1.5%2B-3584e4?logo=gnome&logoColor=white)](https://gnome.pages.gitlab.gnome.org/libadwaita/)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab?logo=python&logoColor=white)](https://www.python.org)

</div>

Janitux is a disk janitor that investigates. Point it at a folder or a whole
disk and, as soon as the scan ends, it names the **main suspects**: huge
single files, big folders buried deep in the tree, caches and forgotten
leftovers, each with the clues against it. Then follow the trail in columns
**sorted by size, biggest first, at every level** (the OmniDiskSweeper way),
look at the **treemap**, and move the culprits to the trash.

![Janitux: the main suspects of a home folder, right after the scan](docs/screenshots/suspects.png)

## Features

- **Main suspects**: a ranked list of what most likely fills your disk, with clues ("single file", "9 levels deep", "untouched for 3 years", "rebuildable cache"…).
- **Columns sorted by size**: always biggest first, at every depth.
- **Treemap and sunburst** of the selected folder. Hover to highlight, click to zoom in.
- **Colors by content**: video, images, audio, archives, documents, code, programs, with a breakdown for every folder.
- **Safe cleaning**: Delete moves to the trash, Shift+Delete deletes for good (it always asks first).
- **Quick hints**: a `cache` badge marks folders that only hold rebuildable data (`.cache`, `node_modules`, `__pycache__`…).
- **Fast and light**: about 250 000 files a second, sizes identical to `du`, hard links counted once. Dependencies: GTK and nothing else.
- English and Italian.

| Treemap | Sunburst, light theme |
|---|---|
| ![Treemap view](docs/screenshots/treemap.png) | ![Sunburst view in the light theme](docs/screenshots/sunburst.png) |

<details>
<summary>Start page: every disk and how full it is</summary>

![Start page](docs/screenshots/start.png)

</details>

## How the suspects are found

Every item of at least 0.5% of the scan (between 10 MB and 1 GB) gets a
suspicion score built like [TF-IDF](https://en.wikipedia.org/wiki/Tf%E2%80%93idf):

```
suspicion(x) = share(x) · ln(1 + N / files(x)) · √depth(x) · bonus(x)
```

| Term | Meaning |
|---|---|
| `share(x)` | fraction of the scanned space taken by `x`: the *term frequency* |
| `ln(1 + N / files(x))` | how concentrated `x` is: the *inverse document frequency*. `N` is the number of files in the scan, `files(x)` the files inside `x` (1 for a file). A huge single file scores highest; a top folder holding half of everything barely counts |
| `√depth(x)` | levels below `/`: big things buried deep are the ones nobody remembers |
| `bonus(x)` | ×2 for rebuildable caches and for what is already in the trash |

Suspects are then picked greedily, *explaining away*: once an item is picked,
its contents leave the race and its size is subtracted from the folders above
it, which are scored again on what is left. So the list never repeats itself,
and the sizes add up to the space it explains. The code is short and tested:
[`janitux/suspects.py`](janitux/suspects.py).

## Install

Grab the file for your system from the [latest release](https://github.com/RemoGrillo/janitux/releases/latest):

| System | Package | Command |
|---|---|---|
| Debian 13+, Ubuntu 24.04+ | `.deb` | `sudo apt install ./janitux_*_all.deb` |
| Fedora 40+ | `.rpm` | `sudo dnf install ./janitux-*.noarch.rpm` |
| Arch Linux | `.pkg.tar.zst` | `sudo pacman -U janitux-*-any.pkg.tar.zst` |
| Any distribution | `.flatpak` | `flatpak install --user janitux-*.flatpak` |
| Any distribution with GTK 4.14+ | `.pyz` (portable, no install) | `chmod +x janitux-*.pyz && ./janitux-*.pyz` |

Or run it straight from the source:

```sh
git clone https://github.com/RemoGrillo/janitux.git && cd janitux
python3 -m janitux            # needs PyGObject, GTK 4.14+, libadwaita 1.5+
```

## Keyboard

| Key | Action |
|---|---|
| ← → ↑ ↓ | move between columns and rows |
| Enter | open a folder / open a file |
| Delete · Shift+Delete | move to trash · delete permanently |
| Backspace | up one level |
| Ctrl+Shift+O · Ctrl+Shift+C | show in file manager · copy path |
| F5 · Ctrl+N | rescan · new scan |

## Build

A plain Makefile, no build system:

```sh
make test          # unit tests
make check         # tests + .desktop and AppStream validation
make pyz           # portable single file
make arch          # Arch package (makepkg)
make deb rpm       # Debian and Fedora packages (nfpm)
make flatpak       # Flatpak bundle (flatpak-builder)
sudo make install  # or PREFIX=/usr, DESTDIR=… for packagers
```

Every push is tested on the oldest supported stack (Ubuntu 24.04: GTK 4.14,
libadwaita 1.5), and every `v*` tag publishes all the packages as a release.

<details>
<summary>How it works</summary>

| File | Role |
|---|---|
| `janitux/scanner.py` | the scan and the size tree (no GUI code, unit tested) |
| `janitux/suspects.py` | the main-suspects ranking (no GUI code, unit tested) |
| `janitux/lineup.py` | the list of suspects and their clues |
| `janitux/columns.py` | the column browser |
| `janitux/charts.py` | sunburst and squarified treemap, drawn with GTK snapshots (GPU) |
| `janitux/inspector.py` | side panel: charts, details, breakdown, actions |
| `janitux/window.py` | scanning, selection, trash and delete |
| `janitux/kinds.py` | file kinds and the color palette (checked for color blindness) |
| `janitux/i18n.py` | translations: add a language by adding a dictionary |

Sizes are disk usage (allocated blocks), so they are what deleting frees.
Memory use is about 260 bytes per file.

</details>

## License

[GPL-3.0-or-later](LICENSE) © Remo Grillo
