"""Brèves du fil : 2 ou 3 infos courtes par passage (titre + 2 phrases), sans page à elles.

Elles s'affichent dans « Le fil » de la page d'accueil, mêlées aux articles, pour que le fil bouge
toute la journée. Stockées par jour dans content/breves/AAAA-MM-JJ.json.
"""
import os
from datetime import timedelta

from . import redaction, sources
from .util import RACINE, ETAT, ecrire_json, heure_locale, lire_json, maintenant, meme_sujet

DOSSIER = RACINE / "content" / "breves"

CONSIGNES = """Tu es journaliste dans une rédaction française sérieuse et neutre. Tu écris des brèves pour un fil d'information.
Pour chaque événement fourni (dépêches de plusieurs médias), écris UNE brève originale.

Règles absolues :
1. Uniquement les faits présents dans les dépêches. N'invente aucun chiffre, date, nom ni citation.
2. Ne recopie aucune phrase : reformule entièrement. Pas de citation entre guillemets.
3. Ton factuel et neutre, aucune opinion. Si une seule source rapporte l'information, emploie le conditionnel.
4. Titre : 70 caractères maximum, informatif, sans point final.
5. Texte : 2 phrases, 45 mots maximum au total, qui disent l'essentiel (quoi, qui, où, et ce que ça change).

Réponds UNIQUEMENT avec un objet JSON valide :
{"breves": [{"id": 1, "titre": "...", "texte": "..."}, ...]}"""


def breves_recentes(heures=36):
    """Brèves des dernières heures (pour l'affichage et pour éviter les doublons)."""
    limite = maintenant() - timedelta(hours=heures)
    tout = []
    for f in sorted(DOSSIER.glob("*.json"))[-3:]:
        tout += lire_json(f, [])
    from datetime import datetime
    return [b for b in tout if datetime.fromisoformat(b["publie_le"]) >= limite]


def _ia(evenements, cfg, journal):
    lignes = []
    for i, ev in enumerate(evenements, 1):
        lignes.append(f"=== Événement {i} ===")
        for d in ev["depeches"][:5]:
            lignes.append(f"- {d['media']} : {d['titre']}. {d['resume'][:300]}")
    messages = [{"role": "system", "content": CONSIGNES}, {"role": "user", "content": "\n".join(lignes)}]
    if os.environ.get("LEFIL_SIMULATION") == "1":
        return [{"id": i, "titre": ev["titre"][:70], "texte": "Brève de démonstration."}
                for i, ev in enumerate(evenements, 1)]
    for f in cfg["ia"]["fournisseurs"]:
        try:
            r = redaction._extraire_json(redaction._appeler(f, messages))
            return r.get("breves", [])
        except Exception as exc:
            journal(f"    ↳ brèves : {f['nom']} a échoué : {exc}")
    return []


def passage(cfg, rubriques, recents, liens_utilises, journal=print, nombre=None):
    """Ajoute quelques brèves au fil. Renvoie le nombre de brèves publiées."""
    p = cfg.get("breves", {})
    nombre = nombre if nombre is not None else p.get("par_passage", 2)
    h = heure_locale(cfg)
    if not nombre or h.hour < p.get("heure_debut", 6) or h.hour >= p.get("heure_fin", 23):
        return 0
    deja = breves_recentes()
    titres_deja = [b["titre"] for b in deja] + [t for b in deja for t in b.get("titres_sources", [])]
    candidats = []
    for rub in rubriques:
        for ev in sources.regrouper(sources.collecter(rub, p.get("fenetre_heures", 4), journal)):
            if any(d["lien"] in liens_utilises for d in ev["depeches"] if d["lien"]):
                continue  # déjà traité en article
            titres = [d["titre"] for d in ev["depeches"]]
            if any(meme_sujet(t, x) for t in titres for x in titres_deja):
                continue  # déjà en brève
            if any(meme_sujet(t, x) for t in titres for a in recents for x in a.get("_titres", [])):
                continue  # déjà un article récent sur le sujet
            ev["rubrique"] = rub["slug"]
            candidats.append(ev)
    # les sujets repris par le plus de médias d'abord, une seule brève par sujet
    candidats.sort(key=lambda e: (e["nb_medias"], e["score"]), reverse=True)
    choisis = []
    for ev in candidats:
        if not any(meme_sujet(ev["titre"], c["titre"]) for c in choisis):
            choisis.append(ev)
        if len(choisis) >= nombre:
            break
    if not choisis:
        journal("Brèves : rien de nouveau")
        return 0
    textes = {int(b.get("id", 0)): b for b in _ia(choisis, cfg, journal) if isinstance(b, dict)}
    fichier = DOSSIER / f"{h.date().isoformat()}.json"
    du_jour = lire_json(fichier, [])
    n = 0
    for i, ev in enumerate(choisis, 1):
        b = textes.get(i)
        if not b or not str(b.get("titre", "")).strip() or not str(b.get("texte", "")).strip():
            continue
        if len(str(b["texte"]).split()) > 70:
            continue
        du_jour.append({
            "titre": str(b["titre"]).strip().rstrip("."),
            "texte": str(b["texte"]).strip(),
            "rubrique": ev["rubrique"],
            "publie_le": maintenant().isoformat(timespec="seconds"),
            "titres_sources": [d["titre"] for d in ev["depeches"]][:4],
        })
        n += 1
        journal(f"Brève : « {b['titre']} »")
    if n:
        ecrire_json(fichier, du_jour)
    return n
