"""Veille : lecture des flux RSS et regroupement des dépêches en « événements »."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser
import requests

from .util import USER_AGENT, maintenant, meme_sujet, mots_cles, nettoyer_html


def _date(entree):
    for cle in ("published_parsed", "updated_parsed"):
        t = entree.get(cle)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def lire_flux(url, timeout=20):
    """Renvoie la liste des dépêches d'un flux (titre, résumé, lien, date, média)."""
    if url.startswith("file://"):
        flux = feedparser.parse(url[7:])
    else:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        r.raise_for_status()
        flux = feedparser.parse(r.content)
    media = (flux.feed.get("title") or urlparse(url).netloc).strip()
    google = "news.google." in url
    depeches = []
    for e in flux.entries:
        titre = nettoyer_html(e.get("title"))
        if not titre:
            continue
        media_dep = media
        if google:
            # Google Actualités : « Titre - Nom du média » ; le résumé ne contient que des liens
            if " - " in titre:
                titre, media_dep = titre.rsplit(" - ", 1)
            src = e.get("source", {})
            media_dep = (src.get("title") if hasattr(src, "get") else None) or media_dep
            e["summary"] = ""
        depeches.append(
            {
                "titre": titre,
                "resume": nettoyer_html(e.get("summary"))[:600],
                "lien": e.get("link", ""),
                "date": _date(e),
                "media": media_dep,
            }
        )
    return depeches


def collecter(rubrique, fenetre_heures, journal=print):
    import re
    limite = maintenant() - timedelta(hours=fenetre_heures)
    filtre = re.compile(rubrique["filtre"], re.I) if rubrique.get("filtre") else None
    exclure = re.compile(rubrique["exclure"], re.I) if rubrique.get("exclure") else None
    toutes = []
    for url in rubrique["flux"]:
        try:
            deps = lire_flux(url)
            journal(f"  ✓ {url} : {len(deps)} dépêches")
        except Exception as exc:  # un flux en panne ne bloque pas les autres
            journal(f"  ✗ {url} : {exc}")
            continue
        deps = [d for d in deps if d["date"] is None or d["date"] >= limite]
        if filtre:
            deps = [d for d in deps if filtre.search(d["titre"] + " " + d["resume"])]
        if exclure:
            deps = [d for d in deps if not exclure.search(d["titre"] + " " + d["resume"])]
        toutes += deps
    return toutes


def regrouper(depeches):
    """Regroupe les dépêches qui parlent du même événement.
    Plus un événement est repris par des médias différents, plus il est important."""
    evenements = []
    for d in sorted(depeches, key=lambda x: x["date"] or maintenant(), reverse=True):
        mc = mots_cles(d["titre"] + " " + d["resume"][:200])
        cible = next(
            (
                ev for ev in evenements
                if any(meme_sujet(d["titre"], x["titre"], d["resume"][:200], x["resume"][:200]) for x in ev["depeches"])
            ),
            None,
        )
        if cible:
            cible["depeches"].append(d)
            cible["mots"] |= mc
        else:
            evenements.append({"depeches": [d], "mots": set(mc)})

    for ev in evenements:
        medias = {d["media"] for d in ev["depeches"]}
        plus_recente = max((d["date"] for d in ev["depeches"] if d["date"]), default=None)
        age_h = (maintenant() - plus_recente).total_seconds() / 3600 if plus_recente else 6
        ev["nb_medias"] = len(medias)
        ev["score"] = len(medias) * 3 + len(ev["depeches"]) - age_h * 0.5
        ev["titre"] = ev["depeches"][0]["titre"]
    evenements.sort(key=lambda e: e["score"], reverse=True)
    return evenements
