"""Minimal translations: English is the source language, other languages
are plain dictionaries. Add a language by adding a dict to CATALOGS."""

import os

IT = {
    # start page
    "Every full disk has a culprit. The janitor is on the case.":
        "Ogni disco pieno ha un colpevole. Il bidello indaga.",
    "Locations": "Posizioni",
    "Home folder": "Cartella personale",
    "Choose a folder…": "Scegli una cartella…",
    "Pick any folder, or drop one on this window": "Scegli una cartella qualsiasi o trascinala su questa finestra",
    "Stay on one filesystem": "Resta su un solo filesystem",
    "Skip other disks and mounts found inside the folder": "Salta altri dischi e mount trovati dentro la cartella",
    "{free} free of {total}": "{free} liberi su {total}",
    # scanning
    "Investigating…": "Indagine in corso…",
    "Cancel": "Annulla",
    "{n} file": "{n} file",
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
    "{n} folder could not be read": "{n} cartella non leggibile",
    "{n} folders could not be read": "{n} cartelle non leggibili",
    "not scanned: other filesystem": "non scansionata: altro filesystem",
    "not readable": "non leggibile",
    "{n} more item": "{n} altro elemento",
    "{n} more items": "altri {n} elementi",
    "cache": "cache",
    "About Janitux": "Informazioni su Janitux",
    # deletion
    "Moved “{name}” to trash ({size})": "“{name}” spostato nel cestino ({size})",
    "Deleted “{name}” ({size})": "“{name}” eliminato ({size})",
    "Delete “{name}” permanently?": "Eliminare definitivamente “{name}”?",
    "{size} in {n} file will be removed. This cannot be undone.":
        "Verranno rimossi {size} in {n} file. L’operazione non è reversibile.",
    "{size} in {n} files will be removed. This cannot be undone.":
        "Verranno rimossi {size} in {n} file. L’operazione non è reversibile.",
    "Delete permanently": "Elimina definitivamente",
    "Could not move to trash": "Impossibile spostare nel cestino",
    "Some items could not be deleted": "Alcuni elementi non sono stati eliminati",
    "Path copied": "Percorso copiato",
    # activity and trash
    "Activity": "Attività",
    "Nothing happened yet": "Ancora niente da registrare",
    "Open the log file": "Apri il file del registro",
    "Investigated {path}: {size} in {n} file": "Analizzata {path}: {size} in {n} file",
    "Investigated {path}: {size} in {n} files": "Analizzata {path}: {size} in {n} file",
    "{size} moved to trash": "{size} nel cestino",
    "Trash": "Cestino",
    "Measuring…": "Misurazione…",
    "Empty…": "Svuota…",
    "Empty trash…": "Svuota il cestino…",
    "{size} in {n} item": "{size} in {n} elemento",
    "{size} in {n} items": "{size} in {n} elementi",
    "The trash is empty": "Il cestino è vuoto",
    "The trash is already empty": "Il cestino è già vuoto",
    "Empty the trash?": "Svuotare il cestino?",
    "{n} item, {size}, will be deleted for good. This cannot be undone.":
        "{n} elemento, {size}, verrà eliminato per sempre. L’operazione non è reversibile.",
    "{n} items, {size} in all, will be deleted for good. This cannot be undone.":
        "{n} elementi, {size} in tutto, verranno eliminati per sempre. L’operazione non è reversibile.",
    "Type “{word}” to confirm.": "Per confermare scrivi “{word}”.",
    "empty": "svuota",
    "Empty trash": "Svuota il cestino",
    "Emptied the trash: {size} freed": "Cestino svuotato: liberati {size}",
    "{n} item could not be deleted": "{n} elemento non è stato eliminato",
    "{n} items could not be deleted": "{n} elementi non sono stati eliminati",
    # suspects
    "Suspects": "Sospettati",
    "Main suspects": "I principali sospettati",
    "{n} suspect holds {size}, {pct} of the scanned space":
        "{n} sospettato occupa {size}, il {pct} dello spazio analizzato",
    "{n} suspects hold {size}, {pct} of the scanned space":
        "{n} sospettati occupano {size}, il {pct} dello spazio analizzato",
    "No suspects: nothing here is big enough to worry about.":
        "Nessun sospettato: qui niente è abbastanza grande da preoccupare.",
    "already in the trash": "già nel cestino",
    "rebuildable cache": "cache rigenerabile",
    "single file": "file singolo",
    "mostly {kind}": "soprattutto {kind}",
    "{n} levels deep": "a {n} livelli di profondità",
    "untouched for {n} months": "fermo da {n} mesi",
    "untouched for {n} years": "fermo da {n} anni",
    "needs admin rights": "servono i permessi di amministratore",
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


def plural(n, one, many, **fields):
    """The sentence for `n` things, with {n} written in the local style."""
    return _(one if n == 1 else many).format(n=f"{n:n}", **fields)


TAGLINE = _("Every full disk has a culprit. The janitor is on the case.")
