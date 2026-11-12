"""Recherche d'une photo libre de droits sur Wikipédia / Wikimedia Commons.

Ordre : 1) photo principale de la page Wikipédia du sujet  2) recherche Commons sur le sujet
3) recherche Commons sur la photo par défaut de la rubrique. Seules les licences libres
(CC BY, CC BY-SA, CC0, domaine public) sont acceptées, avec crédit de l'auteur.
"""
import os
import re

import requests

from .util import ETAT, USER_AGENT, ecrire_json, lire_json, nettoyer_html

# Photos d'illustration déjà utilisées sur le site (Pexels et photos par défaut Commons) :
# on ne les réutilise pas, pour que deux articles n'aient pas la même image.
FICHIER_UTILISEES = ETAT / "photos_utilisees.json"
_utilisees = None


def utilisees():
    global _utilisees
    if _utilisees is None:
        _utilisees = set(lire_json(FICHIER_UTILISEES, []))
    return _utilisees


def marquer_utilisee(photo):
    """À appeler quand une photo est réellement publiée."""
    if photo and cle_de(photo):
        utilisees().add(cle_de(photo))
        ecrire_json(FICHIER_UTILISEES, sorted(utilisees())[-20000:])

WIKI = "https://fr.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
LARGEUR = 1200


_dernier_appel = [0.0]


def _get(url, params):
    """Appel à l'API Wikipédia / Commons, poli : 1 requête par seconde, et on patiente si on est limité (429)."""
    import time
    params = {**params, "format": "json", "formatversion": 2}
    for essai in range(3):
        attente = 1.0 - (time.time() - _dernier_appel[0])
        if attente > 0:
            time.sleep(attente)
        _dernier_appel[0] = time.time()
        r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
        if r.status_code == 429 and essai < 2:
            time.sleep(int(r.headers.get("Retry-After", "0") or 0) or 15 * (essai + 1))
            continue
        r.raise_for_status()
        return r.json()


def _licence_libre(nom):
    n = (nom or "").lower()
    return any(k in n for k in ("cc by", "cc-by", "cc0", "public domain", "domaine public", "pd"))


def _infos_fichier(titre_fichier):
    data = _get(
        COMMONS,
        {
            "action": "query",
            "titles": titre_fichier,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": LARGEUR,
        },
    )
    pages = data.get("query", {}).get("pages", [])
    if not pages or "imageinfo" not in pages[0]:
        return None
    ii = pages[0]["imageinfo"][0]
    if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
        return None
    meta = ii.get("extmetadata", {})
    licence = meta.get("LicenseShortName", {}).get("value", "")
    if not _licence_libre(licence):
        return None
    auteur = nettoyer_html(meta.get("Artist", {}).get("value", "")) or "Auteur inconnu"
    return {
        "url": ii.get("thumburl") or ii["url"],
        "credit": auteur[:120],
        "licence": licence,
        "licence_url": meta.get("LicenseUrl", {}).get("value", ""),
        "page": ii.get("descriptionurl", ""),
        "legende": nettoyer_html(meta.get("ImageDescription", {}).get("value", ""))[:200],
        "source": "Wikimedia Commons",
    }


def _depuis_wikipedia(sujet):
    data = _get(
        WIKI,
        {"action": "query", "titles": sujet, "redirects": 1, "prop": "pageimages", "piprop": "name"},
    )
    pages = data.get("query", {}).get("pages", [])
    if pages and pages[0].get("pageimage"):
        titre = "File:" + pages[0]["pageimage"].replace("_", " ")
        cle = "commons:" + titre
        if cle in utilisees():
            return None  # photo déjà utilisée : on cherchera une autre photo du même sujet sur Commons
        infos = _infos_fichier(titre)
        if infos:
            infos["cle"] = cle
        return infos
    return None


def cle_de(photo):
    """Identifiant stable d'une photo, quelle que soit la façon dont elle a été trouvée."""
    if not photo:
        return None
    if photo.get("cle"):
        return photo["cle"]
    import urllib.parse
    url = photo.get("url", "").split("?")[0]
    if "wikimedia.org" in url:
        nom = url.split("/thumb/")[-1].split("/")[2] if "/thumb/" in url else url.rsplit("/", 1)[-1]
        return "commons:File:" + urllib.parse.unquote(nom).replace("_", " ")
    return url or None


def _recherche_commons(requete, titre_doit_contenir=None):
    data = _get(
        COMMONS,
        {
            "action": "query",
            "list": "search",
            "srsearch": f"{requete} filetype:bitmap",
            "srnamespace": 6,
            "srlimit": 20,
        },
    )
    for res in data.get("query", {}).get("search", []):
        cle = "commons:" + res["title"].replace("_", " ")
        if cle in utilisees():
            continue
        if titre_doit_contenir and not any(m in res["title"].lower() for m in titre_doit_contenir):
            continue
        if titre_doit_contenir and re.search(r"painting|still.life|vanitas|met dp|museum|map|logo|\.svg",
                                              res["title"].lower().replace("_", " ")):
            continue  # pour les illustrations : pas de tableaux, cartes ni logos
        infos = _infos_fichier(res["title"])
        if infos:
            infos["cle"] = cle
            return infos
    return None


PEXELS = "https://api.pexels.com/v1/search"


def recherche_pexels(requete, locale="fr-FR"):
    """Vraie photo d'illustration (banque Pexels, licence gratuite, usage commercial autorisé)."""
    cle = os.environ.get("PEXELS_API_KEY", "").strip()
    if not cle or not requete:
        return None
    r = requests.get(PEXELS, params={"query": requete, "orientation": "landscape", "per_page": 40, "locale": locale},
                     headers={"Authorization": cle, "User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    for ph in r.json().get("photos", []):
        src = ph.get("src", {})
        url = src.get("landscape") or src.get("large")
        cle_photo = f"pexels:{ph.get('id', url)}"
        if url and cle_photo not in utilisees():
            return {
                "cle": cle_photo,
                "url": url,
                "credit": ph.get("photographer", "Pexels"),
                "licence": "Licence Pexels",
                "licence_url": "https://www.pexels.com/fr-fr/license/",
                "page": ph.get("url", "https://www.pexels.com"),
                "legende": (ph.get("alt") or "")[:200],
                "source": "Pexels",
            }
    return None


PIXABAY = "https://pixabay.com/api/"


def recherche_pixabay(requete, lang="fr"):
    """Vraie photo d'illustration Pixabay (licence gratuite, usage commercial autorisé).
    Les règles de Pixabay interdisent l'affichage permanent depuis leurs serveurs :
    la photo est marquée « à télécharger » et copiée sur le site (voir rapatrier)."""
    cle = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not cle or not requete:
        return None
    r = requests.get(PIXABAY, params={"key": cle, "q": requete[:100], "lang": lang, "image_type": "photo",
                                      "orientation": "horizontal", "safesearch": "true", "per_page": 50,
                                      "min_width": 1000},
                     headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    for hit in r.json().get("hits", []):
        cle_photo = f"pixabay:{hit.get('id')}"
        url = hit.get("largeImageURL") or hit.get("webformatURL")
        if url and cle_photo not in utilisees():
            return {
                "cle": cle_photo,
                "url": url,
                "telecharger": True,
                "credit": hit.get("user", "Pixabay"),
                "licence": "Licence Pixabay",
                "licence_url": "https://pixabay.com/fr/service/license-summary/",
                "page": hit.get("pageURL", "https://pixabay.com"),
                "legende": "",
                "source": "Pixabay",
            }
    return None


def recherche_banque(requete, langue="fr"):
    """Banque de photos d'illustration : Pixabay en priorité, Pexels si une clé Pexels existe."""
    photo = recherche_pixabay(requete, lang=langue)
    if not photo and os.environ.get("PEXELS_API_KEY"):
        photo = recherche_pexels(requete, locale="fr-FR" if langue == "fr" else "en-US")
    return photo


def rapatrier(photo, dossier, nom):
    """Copie sur le site une photo qui doit être hébergée chez nous (Pixabay). Renvoie la photo mise à jour."""
    if not photo or not photo.get("telecharger"):
        return photo
    dossier.mkdir(parents=True, exist_ok=True)
    r = requests.get(photo["url"], headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    (dossier / nom).write_bytes(r.content)
    photo = {k: v for k, v in photo.items() if k != "telecharger"}
    photo["url"] = "/photos/" + nom
    return photo


def trouver_photo(sujet, rubrique, journal=print, recherche=""):
    """Ordre : 1) vraie photo du sujet (Wikipédia/Commons)  2) photo d'illustration (Pixabay, ou Pexels)
    3) photo par défaut de la rubrique (Commons puis banque)  4) rien (bandeau coloré)."""
    if os.environ.get("LEFIL_SIMULATION") == "1":
        return None
    defauts = rubrique.get("photos_defaut") or [rubrique.get("photo_defaut", rubrique["nom"])]
    if isinstance(defauts, str):
        defauts = [defauts]
    defauts = list(defauts) + [rubrique["nom"]]   # dernier recours : le nom de la rubrique ou de la ville

    def commons_filtre(requete):
        # photo par défaut : le nom du fichier doit parler du sujet (pas de carte, logo ni tableau)
        mots = [m.lower() for m in requete.replace("-", " ").split() if len(m) > 3]
        return _recherche_commons(requete, titre_doit_contenir=mots or None)

    essais = []
    if sujet:
        essais += [("Wikipédia", _depuis_wikipedia, sujet), ("Commons", _recherche_commons, sujet)]
    if recherche:
        essais.append(("banque de photos", recherche_banque, recherche))
    for d in defauts:
        essais += [("défaut rubrique", commons_filtre, d), ("banque de photos rubrique", recherche_banque, d)]
    for nom, fonction, requete in essais:
        try:
            photo = fonction(requete)
            if photo:
                journal(f"    📷 photo trouvée ({nom} : {requete})")
                return photo
        except Exception as exc:
            journal(f"    📷 {nom} « {requete} » : {exc}")
    return None
