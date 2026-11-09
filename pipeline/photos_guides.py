"""Donne une vraie photo (Pixabay, ou Pexels) à chaque guide qui n'en a pas encore.

    PIXABAY_API_KEY=... python -m pipeline.photos_guides

Pour chaque fichier de content/guides/ ayant une ligne « photo_recherche » et pas encore de « photo_url » :
cherche une photo sur Pexels, la télécharge dans legacy/photos/ (servie depuis le site) et note le crédit.
Ne refait rien pour les guides déjà illustrés : on peut le lancer à chaque passage sans risque.
Pour changer la photo d'un guide : supprime ses lignes photo_url / photo_credit / photo_page.
"""
import os
import re
import sys

import requests

from .photos import marquer_utilisee, recherche_banque
from .util import RACINE, USER_AGENT


def telecharger_choisies():
    """Photos choisies à la main : ligne « photo_telecharger: <adresse> » dans l'en-tête du guide.
    Le fichier est téléchargé une fois dans legacy/photos/ (servi depuis le site, sans lien vers l'extérieur)."""
    dossier = RACINE / "legacy" / "photos"
    dossier.mkdir(parents=True, exist_ok=True)
    for f in sorted((RACINE / "content" / "guides").glob("*.md")):
        entete = f.read_text(encoding="utf-8").split("---", 2)[1]
        m = re.search(r'^photo_telecharger:\s*"?(.+?)"?\s*$', entete, re.M)
        u = re.search(r'^photo_url:\s*"?/photos/(.+?)"?\s*$', entete, re.M)
        if not (m and u) or (dossier / u.group(1)).exists():
            continue
        try:
            r = requests.get(m.group(1), headers={"User-Agent": USER_AGENT}, timeout=60)
            r.raise_for_status()
            (dossier / u.group(1)).write_bytes(r.content)
            print(f"✓ {f.name} : photo choisie téléchargée")
        except Exception as exc:
            print(f"✗ {f.name} : photo choisie non téléchargée ({exc})")


def main():
    telecharger_choisies()
    if not (os.environ.get("PIXABAY_API_KEY") or os.environ.get("PEXELS_API_KEY")):
        print("Aucune clé de banque de photos (PIXABAY_API_KEY) : photos des guides inchangées.")
        return 0
    dossier = RACINE / "legacy" / "photos"
    dossier.mkdir(parents=True, exist_ok=True)
    faits = 0
    for f in sorted((RACINE / "content" / "guides").glob("*.md")):
        t = f.read_text(encoding="utf-8")
        entete = t.split("---", 2)[1]
        if "photo_url:" in entete:
            continue
        m = re.search(r'^photo_recherche:\s*"?(.+?)"?\s*$', entete, re.M)
        if not m:
            continue
        try:
            photo = recherche_banque(m.group(1), langue="en")
        except Exception as exc:
            print(f"✗ {f.name} : {exc}")
            continue
        if not photo:
            print(f"– {f.name} : aucune photo trouvée pour « {m.group(1)} »")
            continue
        image = requests.get(photo["url"], headers={"User-Agent": USER_AGENT}, timeout=60)
        image.raise_for_status()
        nom = f.stem + ".jpg"
        (dossier / nom).write_bytes(image.content)
        ajout = (f'photo_url: "/photos/{nom}"\nphoto_credit: "{photo["credit"].replace(chr(34), "")}"\n'
                 f'photo_page: "{photo["page"]}"\nphoto_source: "{photo.get("source", "Pexels")}"\n')
        t = t.replace("---\n", "---\n" + ajout, 1) if t.startswith("---\n") else t
        f.write_text(t, encoding="utf-8")
        marquer_utilisee(photo)
        faits += 1
        print(f"✓ {f.name} ← photo de {photo['credit']} ({photo.get('source', '')})")
    print(f"{faits} guide(s) illustré(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
