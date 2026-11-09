"""Choisit pour chaque guide une image existante parmi les anciennes pages fusionnées."""
import os, re, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
import plan
from lib import decode_name
SRC = plan.SRC; DEST = sys.argv[1]
fichiers = {decode_name(b)[0]: b for b in os.listdir(SRC.encode())}
lignes = plan.plan_php()
SANS_IMAGE = {"/maison/animal-en-surpoids/", "/argent/emploi-et-travail/", "/beaute/etre-belle-naturellement/",
              "/sante/complements-alimentaires/", "/sante/manger-avant-apres-le-sport/"}
EXCLURE = {"teletravail.png", "comment-faire-maigrir-un-chat-d'appartement.jpg", "manger-davant-la-tele.webp",
           "quel-est-le-meilleur-complement-alimentaire-contre-l'arthrose.jpg", "que-manger-avant-le-sport.jpg",
           "que-manger-le-soir-pour-maigrir.jpg", "top-5-des-methodes-pour-maigrir-du-ventre.webp",
           "est-ce-que-l'ananas-fait-maigrir.jpg", "comment-etre-belle-naturellement-sans-maquillage.jpg"}
gdir = os.path.join(DEST, "content/guides")
for f in sorted(os.listdir(gdir)):
    p = os.path.join(gdir, f); t = open(p, encoding="utf-8").read()
    url = re.search(r"^url: (\S+)", t, re.M).group(1)
    t = re.sub(r"^image: .*\n", "", t, flags=re.M)
    choix = None
    if url in SANS_IMAGE:
        sources = []
    else:
        sources = None
    sources = [] if sources == [] else [l for l in lignes if l["action"] == "guide" and l["cible"] == url]
    sources.sort(key=lambda l: -l["mots"])
    for l in sources:
        stem = l["ancien"].lstrip("/").rsplit(".", 1)[0]
        for ext in (".jpg", ".webp", ".png", ".jpeg"):
            if stem + ext in fichiers and stem + ext not in EXCLURE:
                choix = stem + ext; break
        if choix: break
    if choix:
        shutil.copyfile(os.path.join(SRC.encode(), fichiers[choix]), os.path.join(DEST, "legacy", choix))
        t = t.replace("\nrubrique:", f"\nimage: \"/{choix}\"\nrubrique:", 1)
    open(p, "w", encoding="utf-8").write(t)
    print(("✓ " if choix else "– ") + url + (f"  ← {choix}" if choix else ""))
