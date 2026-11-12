"""Outils communs : config, dates, texte, stockage."""
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

RACINE = Path(__file__).resolve().parent.parent
ARTICLES = RACINE / "content" / "articles"
ETAT = RACINE / "state"

# Wikimedia demande un User-Agent qui identifie le robot avec un moyen de contact (sinon limitation stricte)
USER_AGENT = "LibelilleBot/1.0 (https://www.libelille.fr/a-propos/; robot de veille d'actualite)"

MOTS_VIDES = set(
    """avec dans pour sur sous entre vers chez sans mais plus moins tres apres avant
    dont elle elles ils nous vous leur leurs cette ces cet son ses sont etre avoir
    fait faire comme tout tous toute toutes aussi encore depuis alors ainsi quand
    selon contre deux trois quoi quel quelle quels quelles ete etait sera seront
    direct video videos info infos live""".split()
)


def charger_config():
    with open(RACINE / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def maintenant():
    return datetime.now(timezone.utc)


def heure_locale(cfg, dt=None):
    return (dt or maintenant()).astimezone(ZoneInfo(cfg["site"]["fuseau"]))


def sans_accents(texte):
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


def slugifier(texte, longueur=80):
    s = sans_accents(texte).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:longueur].rstrip("-") or "article"


def mots_cles(texte):
    s = sans_accents(texte or "").lower()
    return {m for m in re.findall(r"[a-z0-9]+", s) if len(m) > 3 and m not in MOTS_VIDES}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def meme_sujet(titre_a, titre_b, texte_a="", texte_b=""):
    """Deux dépêches parlent-elles du même événement ?
    On compare surtout les titres (mots importants en commun), puis le texte complet."""
    ta, tb = mots_cles(titre_a), mots_cles(titre_b)
    commun = len(ta & tb)
    if commun >= 3 and commun / max(1, min(len(ta), len(tb))) >= 0.5:
        return True
    return jaccard(mots_cles(titre_a + " " + texte_a), mots_cles(titre_b + " " + texte_b)) >= 0.25


def nettoyer_html(texte):
    texte = re.sub(r"<[^>]+>", " ", texte or "")
    texte = re.sub(r"&nbsp;|&#160;", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


def lire_json(chemin, defaut):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return defaut


def ecrire_json(chemin, donnees):
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    Path(chemin).write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")


def tous_les_articles():
    arts = [lire_json(p, None) for p in ARTICLES.glob("*.json")]
    arts = [a for a in arts if a]
    arts.sort(key=lambda a: a["publie_le"], reverse=True)
    return arts
