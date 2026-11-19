"""Minimal translations: English is the source language, other languages
are plain dictionaries. Add a language by adding a dict to CATALOGS."""

import os

IT = {
    # start page
    "Find out what is eating your disk": "Scopri cosa occupa il tuo disco",
    "Locations": "Posizioni",
    "Home folder": "Cartella personale",
    "Choose a folder…": "Scegli una cartella…",
    "Pick any folder, or drop one on this window": "Scegli una cartella qualsiasi o trascinala su questa finestra",
    "Stay on one filesystem": "Resta su un solo filesystem",
    "Skip other disks and mounts found inside the folder": "Salta altri dischi e mount trovati dentro la cartella",
    "{free} free of {total}": "{free} liberi su {total}",
    # scanning
    "Scanning…": "Scansione…",
    "Cancel": "Annulla",
    "{n} files": "{n} file",
    # results
    "New scan": "Nuova scansione",
    "Rescan": "Ripeti scansione",
    "Rescan folder": "Ripeti scansione della cartella",
    "Sunburst": "Raggiera",
    "Treemap": "Mappa",
    "Up one level": "Su di un livello",
    "Open": "Apri",
    "Show in folder": "Mostra nella cartella",
    "Copy path": "Copia percorso",
    "Move to trash": "Sposta nel cestino",
    "Delete permanently…": "Elimina definitivamente…",
    "{pct} of folder": "{pct} della cartella",
    "{pct} of total": "{pct} del totale",
    "modified {date}": "modificato il {date}",
    "freed {size}": "liberati {size}",
    "{n} folders could not be read": "{n} cartelle non leggibili",
    "not scanned: other filesystem": "non scansionata: altro filesystem",
    "not readable": "non leggibile",
    "{n} more items": "altri {n} elementi",
    "cache": "cache",
    "About Janitux": "Informazioni su Janitux",
    # deletion
    "Moved “{name}” to trash ({size})": "“{name}” spostato nel cestino ({size})",
    "Deleted “{name}” ({size})": "“{name}” eliminato ({size})",
    "Delete “{name}” permanently?": "Eliminare definitivamente “{name}”?",
    "{size} in {n} files will be removed. This cannot be undone.":
        "Verranno rimossi {size} in {n} file. L’operazione non è reversibile.",
    "Delete permanently": "Elimina definitivamente",
    "Could not move to trash": "Impossibile spostare nel cestino",
    "Some items could not be deleted": "Alcuni elementi non sono stati eliminati",
    "Path copied": "Percorso copiato",
    # file kinds
    "Video": "Video",
    "Images": "Immagini",
    "Audio": "Audio",
    "Archives & disk images": "Archivi e immagini disco",
    "Documents": "Documenti",
    "Code": "Codice",
    "Programs & libraries": "Programmi e librerie",
    "Other": "Altro",
}

CATALOGS = {"it": IT}


def _language():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return value.split(":")[0][:2].lower()
    return "en"


_catalog = CATALOGS.get(_language(), {})


def _(text: str) -> str:
    return _catalog.get(text, text)
