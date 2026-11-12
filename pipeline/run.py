"""Un passage du robot : veille → choix des sujets → rédaction → photo → enregistrement.

Lancé toutes les heures par GitHub Actions :  python -m pipeline.run
"""
import math
import os
import sys
from datetime import timedelta

from . import breves, photos, redaction, sources
from .util import (
    RACINE,
    ARTICLES, ETAT, charger_config, ecrire_json, heure_locale, lire_json,
    maintenant, meme_sujet, slugifier, tous_les_articles,
)

class _SeulementBreves(Exception):
    pass


def quota_du_passage(cfg, publies_aujourdhui):
    """Étale les publications sur la journée au lieu de tout publier le matin."""
    p = cfg["publication"]
    total = p["articles_par_jour"]
    force = os.environ.get("LEFIL_QUOTA", "").strip()
    if force.isdigit():  # lancement manuel : « publie N articles maintenant »
        return min(int(force), total - publies_aujourdhui)
    h = heure_locale(cfg)
    if p.get("creneaux"):
        # objectif cumulé : tout ce qui était prévu jusqu'à l'heure actuelle doit être publié
        cible = sum(n for hh, n in p["creneaux"].items() if int(hh) <= h.hour)
        return max(0, min(p["max_par_passage"], cible - publies_aujourdhui, total - publies_aujourdhui))
    heure = h.hour + h.minute / 60
    if heure < p["heure_debut"] or heure >= p["heure_fin"]:
        return 0
    avancement = (heure - p["heure_debut"] + 1) / (p["heure_fin"] - p["heure_debut"])
    cible = math.ceil(total * min(avancement, 1.0)) + 1
    return max(0, min(p["max_par_passage"], cible - publies_aujourdhui, total - publies_aujourdhui))


def en_silence_electoral(rub, cfg):
    """Pas d'article de la rubrique électorale la veille et le jour du scrutin jusqu'à 20h
    (interdiction de publier sondages et résultats, silence de campagne)."""
    from datetime import date, timedelta as td
    h = heure_locale(cfg)
    for j in rub.get("blackout_scrutins", []):
        jour = date.fromisoformat(j)
        if h.date() == jour - td(days=1) or (h.date() == jour and h.hour < 20):
            return True
    return False


def deja_traite(evenement, recents, liens_utilises):
    """Vrai si une dépêche a déjà servi, ou si un article récent couvre le même sujet."""
    if any(d["lien"] in liens_utilises for d in evenement["depeches"] if d["lien"]):
        return True
    return any(
        meme_sujet(d["titre"], t) for d in evenement["depeches"] for a in recents for t in a["_titres"]
    )


def compter_mots(texte):
    return len(texte.split())


IMPORTANT_DEFAUT = (r"accident|incendie|explosion|mort|décès|deces|tué|tue |blessé|blesse|fusillade|agression|évacu|evacu|"
                    r"alerte|vigilance|inondation|tempête|tempete|orage|grève|greve|coupure|panne|fermé|ferme |fermeture|"
                    r"bouchon|bloqué|bloque|perturb|manifestation|interpell|enquête|enquete|disparition|effondrement")


def age_heures(ev):
    dates = [d["date"] for d in ev["depeches"] if d["date"]]
    return (maintenant() - max(dates)).total_seconds() / 3600 if dates else 0


def main(journal=print):
    import re
    cfg = charger_config()
    jour = heure_locale(cfg).date().isoformat()
    heure = heure_locale(cfg).hour

    articles = tous_les_articles()
    aujourdhui = [a for a in articles if heure_locale(cfg, _dt(a["publie_le"])).date().isoformat() == jour]
    limite_recents = maintenant() - timedelta(hours=48)
    recents = [a for a in articles if _dt(a["publie_le"]) >= limite_recents]
    for a in recents:
        a["_titres"] = [a["titre"]] + [s["titre"] for s in a.get("sources", [])]
    liens_utilises = set(lire_json(ETAT / "liens_utilises.json", []))

    reguliers = [r for r in cfg["rubriques"] if not r.get("declenchement")]
    evenementiels = [r for r in cfg["rubriques"] if r.get("declenchement")]
    slugs_reg = {r["slug"] for r in reguliers}
    du_jour = lambda slug: sum(1 for a in aujourdhui if a["rubrique"] == slug)  # noqa: E731
    publies_total = 0

    echecs_ia = [0]  # échecs de rédaction consécutifs

    def publier(ev, rub):
        """Rédige et publie un événement. Renvoie True si l'article est en ligne."""
        journal(f"→ {rub['nom']} : « {ev['titre']} » ({ev['nb_medias']} média(s))")
        try:
            art, modele = redaction.rediger(ev, rub, cfg, journal)
            echecs_ia[0] = 0
        except redaction.EchecRedaction as exc:
            journal(f"   ✗ rédaction impossible : {exc}")
            echecs_ia[0] += 1
            if "absente" in str(exc) or "quota" in str(exc) or echecs_ia[0] >= 3:
                raise
            return False
        nb_mots = compter_mots(art["chapeau"] + " " + art["corps"])
        if nb_mots < cfg["publication"]["mots_min"]:
            journal(f"   ✗ trop court ({nb_mots} mots), rejeté")
            return False
        photo = photos.trouver_photo(art.get("sujet_photo", "").strip(), rub, journal,
                                     recherche=str(art.get("recherche_photo", "")).strip())
        if not photo and os.environ.get("LEFIL_SIMULATION") != "1":
            # jamais d'article sans image : on n'enregistre pas, le sujet reste disponible pour le passage suivant
            journal("   ✗ aucune photo trouvée : article non publié (nouvel essai au prochain passage)")
            return False
        if photo and photo.get("telecharger"):
            import hashlib
            try:
                nom = "actu-" + hashlib.md5(photo["cle"].encode()).hexdigest()[:12] + ".jpg"
                photo = photos.rapatrier(photo, RACINE / "legacy" / "photos", nom)
            except Exception as exc:
                journal(f"   📷 copie de la photo impossible : {exc}")
                photo = None
        enregistrer(art, ev, rub, photo, modele)
        photos.marquer_utilisee(photo)
        liens_utilises.update(d["lien"] for d in ev["depeches"] if d["lien"])
        recents.append({"_titres": [art["titre"]] + [d["titre"] for d in ev["depeches"]]})
        aujourdhui.append({"rubrique": rub["slug"]})
        journal(f"   ✓ publié ({nb_mots} mots{', avec photo' if photo else ', sans photo'})")
        return True

    # une seule lecture des flux par rubrique et par passage (articles + brèves)
    _cache, _collecter = {}, sources.collecter
    def collecter_cache(rub, fenetre, journal=journal):
        cle = (rub["slug"], fenetre)
        if cle not in _cache:
            _cache[cle] = _collecter(rub, fenetre, journal)
        return _cache[cle]
    sources.collecter = collecter_cache

    reparer_photos(cfg, journal)

    mode = os.environ.get("LEFIL_MODE", "").strip()
    try:
        if mode == "breves":
            raise _SeulementBreves
        # ── A. Rubriques régulières (national, présidentielle) : étalées sur la journée ──
        n_reg = sum(1 for a in aujourdhui if a["rubrique"] in slugs_reg)
        a_publier = quota_du_passage(cfg, n_reg)
        journal(f"{n_reg} article(s) national(aux) aujourd'hui · {a_publier} à publier ce passage")
        candidats = []
        if a_publier:
            for rub in reguliers:
                if en_silence_electoral(rub, cfg):
                    journal(f"[{rub['nom']}] pause : veille ou jour de scrutin (silence électoral jusqu'à 20h)")
                    continue
                deja = du_jour(rub["slug"])
                if deja >= rub["quota"]:
                    journal(f"[{rub['nom']}] quota du jour atteint ({deja}/{rub['quota']})")
                    continue
                journal(f"[{rub['nom']}] veille ({deja}/{rub['quota']})")
                for ev in sources.regrouper(sources.collecter(rub, cfg["publication"]["fenetre_heures"], journal)):
                    if not deja_traite(ev, recents, liens_utilises):
                        ev["priorite"] = ev["score"] + (rub["quota"] - deja) * 1.5 + (rub.get("priorite", 0) if deja == 0 else 0)
                        candidats.append((ev, rub))
        candidats.sort(key=lambda c: c[0]["priorite"], reverse=True)
        nb_rubs = max(1, len({r["slug"] for _, r in candidats}))
        max_par_rub = math.ceil(a_publier / nb_rubs) if a_publier else 0
        publies, par_rub = 0, {}
        for ev, rub in candidats:
            if publies >= a_publier:
                break
            if par_rub.get(rub["slug"], 0) >= max_par_rub or du_jour(rub["slug"]) >= rub["quota"]:
                continue
            if deja_traite(ev, recents, liens_utilises):
                continue
            if publier(ev, rub):
                par_rub[rub["slug"]] = par_rub.get(rub["slug"], 0) + 1
                publies += 1
        publies_total += publies

        # ── B. Rubriques déclenchées par l'actualité (villes) ──
        # Avant l'heure de rattrapage : on ne publie que si une info importante tombe.
        # À partir de l'heure de rattrapage : si rien n'a été publié pour la ville, on prend le meilleur sujet du jour.
        locaux = 0
        for rub in evenementiels:
            d = rub["declenchement"]
            if heure < d.get("debut", 8) or du_jour(rub["slug"]) >= rub["quota"]:
                continue
            if locaux >= d.get("max_par_passage", 4):
                break
            # le rattrapage ne concerne que les villes sans aucun article aujourd'hui ;
            # un 2e article n'est publié que pour une info importante
            rattrapage = heure >= d.get("rattrapage", 17) and du_jour(rub["slug"]) == 0
            important = re.compile(d.get("mots_importants", IMPORTANT_DEFAUT), re.I)
            fenetre = d.get("fenetre_rattrapage", 16) if rattrapage else cfg["publication"]["fenetre_heures"]
            evs = [ev for ev in sources.regrouper(sources.collecter(rub, fenetre, journal))
                   if not deja_traite(ev, recents, liens_utilises)]
            if not rattrapage:
                evs = [ev for ev in evs if age_heures(ev) <= d.get("fraicheur_heures", 4) and (
                    ev["nb_medias"] >= d.get("seuil_medias", 2)
                    or important.search(" ".join(x["titre"] for x in ev["depeches"])))]
            if not evs:
                if du_jour(rub["slug"]) > 0:
                    journal(f"[{rub['nom']}] déjà un article aujourd'hui, pas de 2e info importante")
                else:
                    journal(f"[{rub['nom']}] pas d'info importante pour l'instant"
                            + ("" if rattrapage else f" (rattrapage à {d.get('rattrapage', 17)}h)"))
                continue
            ev = max(evs, key=lambda e: e["score"])
            journal(f"[{rub['nom']}] {'rattrapage : meilleur sujet du jour' if rattrapage else 'info importante détectée'}")
            if publier(ev, rub):
                locaux += 1
        publies_total += locaux
    except _SeulementBreves:
        journal("Passage de la demi-heure : brèves seulement")
    except redaction.EchecRedaction:
        journal("Arrêt : fournisseurs d'IA indisponibles (clé absente ou invalide, modèle retiré ou quota atteint).")

    # ── C. Brèves du fil (à chaque passage) ──
    try:
        rubs_breves = [r for r in reguliers if not en_silence_electoral(r, cfg)]
        nb_breves = breves.passage(cfg, rubs_breves, recents, liens_utilises, journal)
        journal(f"{nb_breves} brève(s) ajoutée(s) au fil.")
    except Exception as exc:  # une brève ratée ne doit jamais bloquer le site
        journal(f"Brèves : erreur {exc}")
    sources.collecter = _collecter

    ecrire_json(ETAT / "liens_utilises.json", sorted(liens_utilises)[-3000:])
    journal(f"Terminé : {publies_total} article(s) publié(s).")
    return publies_total


def _sujet_depuis_photo(photo):
    """« Teddy_Riner_Cannes_2016.jpg » → « Teddy Riner Cannes » : pour chercher une AUTRE photo du même sujet."""
    import re as _re
    import urllib.parse
    nom = urllib.parse.unquote((photo or {}).get("url", "").split("?")[0].rsplit("/", 1)[-1])
    nom = _re.sub(r"^\d+px-", "", nom.rsplit(".", 1)[0]).replace("_", " ")
    nom = _re.sub(r"\(.*?\)|\b\d+\b|\bcrop(ped)?\b|\b\d+x\d+\b", " ", nom, flags=_re.I)
    return " ".join(nom.split()[:5])


def _nom_propre_du_titre(titre):
    """Premier nom de personne ou de lieu du titre (« Maël de Calan qualifie… » → « Maël de Calan »)."""
    import re as _re
    mots_vides = {"Le", "La", "Les", "Un", "Une", "Des", "En", "Au", "Aux", "À", "Pour", "Présidentielle", "Vidéo"}
    for m in _re.finditer(r"[A-ZÉÈÀÂÎÔ][\w'’-]+(?:\s+(?:de|du|des|d’|d'|la|le)?\s*[A-ZÉÈÀÂÎÔ][\w'’-]+)+", titre):
        mots = m.group(0).split()
        while mots and mots[0] in mots_vides:
            mots = mots[1:]
        if len(mots) >= 2:
            return " ".join(mots)
    return ""


def reparer_photos(cfg, journal=print, max_par_passage=3):
    """Articles des 7 derniers jours sans image, ou avec une image déjà utilisée par un article plus ancien :
    on leur cherche une autre photo (d'abord du même sujet, sinon la photo par défaut de la rubrique/ville)."""
    if os.environ.get("LEFIL_SIMULATION") == "1":
        return
    rubs = {r["slug"]: r for r in cfg["rubriques"]}
    limite = maintenant() - timedelta(days=7)
    tous = []
    for f in ARTICLES.glob("*.json"):
        a = lire_json(f, None)
        if a:
            tous.append((a["publie_le"], f, a))
    tous.sort(key=lambda x: x[0])
    vues = set()
    a_refaire = []
    for _, f, a in tous:
        cle = photos.cle_de(a.get("photo"))
        if cle:
            photos.utilisees().add(cle)  # tout ce qui est déjà en ligne compte comme utilisé
        if (not a.get("photo") or cle in vues) and _dt(a["publie_le"]) >= limite and a["rubrique"] in rubs:
            a_refaire.append((f, a))
        if cle:
            vues.add(cle)
    faits = 0
    for f, a in a_refaire[:max_par_passage]:
        ancienne = a.get("photo")
        photo = None
        for sujet in [_nom_propre_du_titre(a["titre"]), _sujet_depuis_photo(ancienne) if ancienne else ""]:
            if sujet:
                photo = photos.trouver_photo(sujet, rubs[a["rubrique"]], journal)
                if photo:
                    break
        if not photo:
            photo = photos.trouver_photo("", rubs[a["rubrique"]], journal)
        if photo and photo.get("telecharger"):
            import hashlib
            try:
                nom = "actu-" + hashlib.md5(photo["cle"].encode()).hexdigest()[:12] + ".jpg"
                photo = photos.rapatrier(photo, RACINE / "legacy" / "photos", nom)
            except Exception:
                photo = None
        if photo:
            a["photo"] = photo
            ecrire_json(f, a)
            photos.marquer_utilisee(photo)
            journal(f"📷 {'nouvelle photo (doublon)' if ancienne else 'photo ajoutée'} : « {a['titre']} »")
            faits += 1


def enregistrer(art, ev, rub, photo, modele):
    date = maintenant()
    base = slugifier(art["titre"])
    slug, n = base, 2
    while (ARTICLES / f"{slug}.json").exists():
        slug, n = f"{base}-{n}", n + 1
    vus, sources_art = set(), []
    for d in ev["depeches"]:
        if d["lien"] and d["media"] not in vus:
            vus.add(d["media"])
            sources_art.append({"media": d["media"], "titre": d["titre"], "url": d["lien"]})
    ecrire_json(
        ARTICLES / f"{slug}.json",
        {
            "slug": slug,
            "titre": art["titre"].strip().rstrip("."),
            "chapeau": art["chapeau"].strip(),
            "corps": art["corps"].strip(),
            "mots_cles": [str(m) for m in art.get("mots_cles", [])][:5],
            "rubrique": rub["slug"],
            "publie_le": date.isoformat(timespec="seconds"),
            "photo": photo,
            "sources": sources_art[:6],
            "modele": modele,
        },
    )


def _dt(iso):
    from datetime import datetime
    return datetime.fromisoformat(iso)


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
