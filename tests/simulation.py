"""Test hors ligne : faux flux RSS + IA simulée, dans une copie du projet.

    python tests/simulation.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="lefil-test-"))
shutil.copytree(SRC, TMP / "p", ignore=shutil.ignore_patterns("public", ".git", "content", "state"))
P = TMP / "p"
(P / "content" / "articles").mkdir(parents=True)
(P / "state").mkdir()

now = datetime.now(timezone.utc)
SUJETS = {
    "presidentielle": [("Présidentielle 2027 : un candidat dévoile son programme économique", "Le candidat a présenté ses propositions sur les salaires et la fiscalité lors d'un meeting."),
                       ("Présidentielle : le candidat détaille son programme économique", "Salaires, impôts : les principales mesures présentées dimanche."),
                       ("Budget 2027 : vote au Sénat", "Les sénateurs examinent la partie recettes.")],
    "politique": [("Le gouvernement présente son projet de budget pour 2027", "Le Premier ministre a détaillé les grandes lignes du budget 2027 devant l'Assemblée nationale."),
                  ("Budget 2027 : le gouvernement dévoile ses arbitrages", "Les principales mesures du projet de loi de finances pour 2027 ont été présentées."),
                  ("Municipales : les partis préparent leurs listes", "À quelques mois du scrutin, les formations politiques affinent leurs stratégies.")],
    "international": [("Sommet européen à Bruxelles sur la défense commune", "Les dirigeants des Vingt-Sept se réunissent pour discuter de la défense européenne."),
                      ("Défense : sommet des dirigeants européens à Bruxelles", "Réunion des chefs d'Etat européens sur la défense commune.")],
    "economie": [("L'inflation ralentit en octobre selon l'Insee", "L'indice des prix à la consommation progresse moins vite qu'en septembre.")],
    "societe": [("Grève dans les transports franciliens jeudi", "Plusieurs syndicats appellent à la mobilisation sur le réseau RATP.")],
    "sport": [("Ligue 1 : le PSG s'impose face à Marseille", "Le Paris Saint-Germain a remporté le classique dimanche soir au Parc des Princes.")],
    "tech": [("Une nouvelle loi européenne encadre les plateformes", "Bruxelles adopte de nouvelles obligations pour les grandes plateformes numériques.")],
}


def rss(media, items):
    corps = "".join(
        f"<item><title>{t}</title><description>{d}</description><link>https://{media}.example/{i}-{abs(hash(t))}</link>"
        f"<pubDate>{format_datetime(now - timedelta(minutes=30 + 7 * i))}</pubDate></item>"
        for i, (t, d) in enumerate(items)
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{media}</title>{corps}</channel></rss>'


cfg = (P / "config.yaml").read_text(encoding="utf-8")
for slug, items in SUJETS.items():
    fichiers = []
    for j, media in enumerate(["MediaA", "MediaB"]):
        f = TMP / f"{slug}-{media}.xml"
        f.write_text(rss(media, items[j::2] if len(items) > 1 else items), encoding="utf-8")
        fichiers.append(f"file://{f}")
    # remplace les flux de la rubrique par les faux flux
    cfg = re.sub(
        rf"(slug: {slug}\n(?:.*\n)*?    flux:\n)((?:      - .*\n)+)",
        lambda m: m.group(1) + "".join(f"      - {x}\n" for x in fichiers),
        cfg,
        count=1,
    )
(P / "config.yaml").write_text(cfg, encoding="utf-8")

env = {**os.environ, "LEFIL_SIMULATION": "1", "LEFIL_QUOTA": "10"}
print("=== Passage 1 ===")
subprocess.run([sys.executable, "-m", "pipeline.run"], cwd=P, env=env, check=True)
print("\n=== Passage 2 (doit éviter les doublons) ===")
subprocess.run([sys.executable, "-m", "pipeline.run"], cwd=P, env=env, check=True)
subprocess.run([sys.executable, "build.py"], cwd=P, env=env, check=True)
print("\nArticles :", sorted(p.name for p in (P / "content" / "articles").glob("*.json")))
print("Dossier de test :", P)
