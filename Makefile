# Janitux — plain Makefile, no build system needed.
#
#   make run                  run from the source tree
#   make test                 unit tests (no display needed)
#   make check                tests + desktop/AppStream validation
#   make install              install (PREFIX=/usr/local, DESTDIR for packaging)
#   make pyz                  portable single file:  dist/janitux-VERSION.pyz
#   make dist                 source tarball:        dist/janitux-VERSION.tar.gz
#   make arch                 Arch Linux package:    dist/janitux-VERSION-1-any.pkg.tar.zst
#   make deb rpm              Debian/Fedora packages in dist/ (needs nfpm)
#   make flatpak              Flatpak bundle:        dist/janitux-VERSION.flatpak (needs flatpak-builder)

PREFIX  ?= /usr/local
DESTDIR ?=
PYTHON  ?= python3
SHEBANG ?= /usr/bin/python3
COMPILE ?= 1          # byte-compile on install (0: leave it to the target system)
NFPM    ?= nfpm

APP_ID  := io.github.RemoGrillo.Janitux
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' janitux/__init__.py)

BINDIR     = $(PREFIX)/bin
DATADIR    = $(PREFIX)/share
PKGDATADIR = $(DATADIR)/janitux

SOURCES = $(wildcard janitux/*.py)
DIST_FILES = $(SOURCES) $(wildcard tests/*.py) data Makefile README.md LICENSE packaging

.PHONY: all run test check install uninstall pyz dist arch deb rpm flatpak clean

all: build/janitux

build/janitux: Makefile
	@mkdir -p build
	printf '#!%s\nimport sys\nsys.path.insert(0, "%s")\nfrom janitux.__main__ import main\nsys.exit(main())\n' \
		'$(SHEBANG)' '$(PKGDATADIR)' > $@

run:
	$(PYTHON) -m janitux

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

check: test
	desktop-file-validate data/$(APP_ID).desktop
	appstreamcli validate --no-net data/$(APP_ID).metainfo.xml

install: build/janitux
	install -Dm755 build/janitux $(DESTDIR)$(BINDIR)/janitux
	install -Dm644 -t $(DESTDIR)$(PKGDATADIR)/janitux $(SOURCES)
	if [ "$(strip $(COMPILE))" = 1 ]; then \
		$(PYTHON) -m compileall -q -d $(PKGDATADIR)/janitux $(DESTDIR)$(PKGDATADIR)/janitux; fi
	install -Dm644 data/$(APP_ID).desktop $(DESTDIR)$(DATADIR)/applications/$(APP_ID).desktop
	install -Dm644 data/$(APP_ID).metainfo.xml $(DESTDIR)$(DATADIR)/metainfo/$(APP_ID).metainfo.xml
	install -Dm644 data/icons/hicolor/scalable/apps/$(APP_ID).svg \
		$(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APP_ID).svg

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/janitux
	rm -rf $(DESTDIR)$(PKGDATADIR)
	rm -f $(DESTDIR)$(DATADIR)/applications/$(APP_ID).desktop
	rm -f $(DESTDIR)$(DATADIR)/metainfo/$(APP_ID).metainfo.xml
	rm -f $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APP_ID).svg

pyz:
	rm -rf build/pyz && mkdir -p build/pyz/janitux dist
	cp $(SOURCES) build/pyz/janitux/
	printf 'import sys\nfrom janitux.__main__ import main\nsys.exit(main())\n' > build/pyz/__main__.py
	$(PYTHON) -m zipapp build/pyz -p '/usr/bin/env python3' -o dist/janitux-$(VERSION).pyz
	@echo "-> dist/janitux-$(VERSION).pyz"

dist:
	@mkdir -p dist
	tar --exclude=__pycache__ --transform 's,^,janitux-$(VERSION)/,' \
		-czf dist/janitux-$(VERSION).tar.gz $(DIST_FILES)
	@echo "-> dist/janitux-$(VERSION).tar.gz"

# The PKGBUILD is the AUR one: it finds the local tarball first, so it builds
# the working tree (checksums skipped, they belong to the release tarball).
arch: dist
	rm -rf build/arch && mkdir -p build/arch
	cp packaging/arch/PKGBUILD dist/janitux-$(VERSION).tar.gz build/arch/
	cd build/arch && makepkg -f --cleanbuild --skipchecksums
	cp build/arch/janitux-$(VERSION)-*-any.pkg.tar.zst dist/
	@echo "-> install with: sudo pacman -U dist/janitux-$(VERSION)-*-any.pkg.tar.zst"

build/staging: $(SOURCES) Makefile
	rm -rf $@
	$(MAKE) install DESTDIR=$(CURDIR)/$@ PREFIX=/usr COMPILE=0

deb rpm: build/staging
	@mkdir -p dist
	VERSION=$(VERSION) $(NFPM) package -f packaging/nfpm.yaml -p $@ -t dist/

flatpak:
	@mkdir -p dist
	flatpak-builder --user --install-deps-from=flathub --disable-rofiles-fuse --force-clean \
		--repo=build/flatpak-repo build/flatpak packaging/flatpak/$(APP_ID).yml
	flatpak build-bundle build/flatpak-repo dist/janitux-$(VERSION).flatpak $(APP_ID) \
		--runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo

clean:
	rm -rf build dist .flatpak-builder
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
