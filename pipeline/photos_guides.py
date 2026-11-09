"""Donne une vraie photo (Pexels) à chaque guide qui n'en a pas encore.

    PEXELS_API_KEY=... python -m pipeline.photos_guides

Pour chaque fichier de content/guides/ ayant une ligne « photo_recherche » et pas encore de « photo_url » :
cherche une photo sur Pexels, la télécharge dans legacy/photos/ (servie depuis le site) et note le crédit.
Ne refait rien pour les guides déjà illustrés : on peut le lancer à chaque passage sans risque.
Pour changer la photo d'un guide : supprime ses lignes photo_url / photo_credit / photo_page.
"""
import os
import re
import sys

import requests

from .photos import marquer_utilisee, recherche_pexels
from .util import RACINE, USER_AGENT


def main():
    if not os.environ.get("PEXELS_API_KEY"):
        print("PEXELS_API_KEY absente : photos des guides inchangées.")
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
            photo = recherche_pexels(m.group(1), locale="en-US")
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
                 f'photo_page: "{photo["page"]}"\n')
        t = t.replace("---\n", "---\n" + ajout, 1) if t.startswith("---\n") else t
        f.write_text(t, encoding="utf-8")
        marquer_utilisee(photo)
        faits += 1
        print(f"✓ {f.name} ← photo de {photo['credit']} (Pexels)")
    print(f"{faits} guide(s) illustré(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
