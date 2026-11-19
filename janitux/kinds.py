"""File categories and the one color scheme shared by every view.

Colors follow the *kind of content*: a file gets the color of its kind, a
folder the color of the kind that takes most of its space. The hues and their
order come from a colorblind-validated categorical palette (adjacent pairs
checked in both light and dark mode); "Other" is a neutral gray.
"""

from .i18n import _

VIDEO, IMAGE, AUDIO, ARCHIVE, DOCUMENT, CODE, PROGRAM, OTHER = range(8)
COUNT = 8

NAMES = (
    _("Video"),
    _("Images"),
    _("Audio"),
    _("Archives & disk images"),
    _("Documents"),
    _("Code"),
    _("Programs & libraries"),
    _("Other"),
)

ICONS = (
    "video-x-generic-symbolic",
    "image-x-generic-symbolic",
    "audio-x-generic-symbolic",
    "package-x-generic-symbolic",
    "x-office-document-symbolic",
    "text-x-script-symbolic",
    "application-x-executable-symbolic",
    "text-x-generic-symbolic",
)

_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#898781")
_DARK = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#76756f")


def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))


PALETTE_LIGHT = tuple(_rgb(c) for c in _LIGHT)
PALETTE_DARK = tuple(_rgb(c) for c in _DARK)

# Text drawn on top of a fill: white everywhere except on yellow.
INK_ON = tuple((0.04, 0.04, 0.04) if k == ARCHIVE else (1.0, 1.0, 1.0) for k in range(COUNT))

_EXTENSIONS = {
    VIDEO: "mp4 m4v mkv webm avi mov wmv flv mpg mpeg mts m2ts 3gp ogv vob",
    IMAGE: "jpg jpeg png gif webp bmp tif tiff heic heif avif jxl svg ico psd xcf kra "
           "raw cr2 cr3 nef arw dng orf rw2 raf",
    AUDIO: "mp3 flac wav ogg oga opus m4a aac wma aif aiff ape mid midi",
    ARCHIVE: "zip tar gz tgz bz2 xz txz zst lz lz4 lzma 7z rar cab iso img dmg qcow2 vdi "
             "vmdk vhd vhdx raw-img deb rpm apk pkg snap flatpak appimage squashfs sfs",
    DOCUMENT: "pdf epub mobi djvu doc docx odt rtf txt md tex xls xlsx ods csv ppt pptx odp "
              "pages numbers key",
    CODE: "py c h cc cpp hpp rs go java kt js mjs cjs jsx tsx vue svelte css scss sass html htm "
          "xml json yaml yml toml ini cfg sh bash zsh fish rb php pl lua swift cs r jl zig hs ml "
          "sql ipynb",
    PROGRAM: "so a o ko dll exe msi bin jar class pyc pyo whl wasm node",
}
_BY_EXT = {ext: kind for kind, exts in _EXTENSIONS.items() for ext in exts.split()}


def kind_of(name: str, executable: bool = False, size: int = 0) -> int:
    """Guess the kind of a file from its name, executable bit and size."""
    dot = name.rfind(".")
    if dot > 0:
        ext = name[dot + 1:].lower()
        if ext == "ts":  # TypeScript source, or an MPEG transport stream?
            return VIDEO if size > 8 << 20 else CODE
        kind = _BY_EXT.get(ext)
        if kind is not None:
            return kind
        if ".so." in name:  # versioned shared library: libfoo.so.1.2
            return PROGRAM
    return PROGRAM if executable else OTHER
