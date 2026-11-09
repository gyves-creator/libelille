"""Plan de migration de libelille.fr : chaque ancienne page reçoit une action.

Actions :
  asis     -> copiée telle quelle, même adresse (optique / audition)
  import   -> contenu repris dans le nouveau design, même adresse
  guide    -> fusionnée dans un guide (redirection 301 vers le guide)
  redirect -> redirection 301 vers une autre page
  gone     -> supprimée (code 410)
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib import SRC, decode_name, lire, texte, titre  # noqa: E402

# ── Guides (adresse -> titre, rubrique) ───────────────────────────────────
GUIDES = {
    # Minceur
    "/sante/maigrir-les-bases/": ("Maigrir : les bases pour perdre du poids durablement", "sante"),
    "/sante/aliments-qui-font-maigrir/": ("Les aliments qui aident vraiment à maigrir", "sante"),
    "/sante/sport-et-perte-de-poids/": ("Sport et perte de poids : ce qui marche vraiment", "sante"),
    "/sante/pourquoi-je-ne-maigris-pas/": ("Pourquoi je ne maigris pas ? Les vraies raisons", "sante"),
    "/sante/maigrir-vite/": ("Maigrir vite : ce qui est possible, et ce qui est dangereux", "sante"),
    "/sante/regimes-et-calories/": ("Régimes, calories, jeûne : faire le tri", "sante"),
    "/sante/maigrir-du-ventre/": ("Maigrir du ventre : le guide complet", "sante"),
    "/sante/maigrir-cuisses-et-jambes/": ("Affiner ses cuisses et ses jambes", "sante"),
    "/sante/maigrir-bras-et-visage/": ("Affiner ses bras et son visage", "sante"),
    "/sante/que-manger-le-soir/": ("Que manger le soir pour garder la ligne ?", "sante"),
    "/sante/maigrir-selon-age-et-profil/": ("Maigrir selon son âge et sa situation", "sante"),
    "/sante/maigrir-naturellement/": ("Maigrir naturellement, sans se priver", "sante"),
    # Santé
    "/sante/perte-de-poids-involontaire/": ("Perte de poids inexpliquée : quand s'inquiéter ?", "sante"),
    "/sante/prendre-du-poids/": ("Trop mince ? Prendre du poids sainement", "sante"),
    "/maison/animal-en-surpoids/": ("Chien, chat, cheval : gérer le poids de son animal", "maison"),
    "/sante/surpoids-et-obesite/": ("Surpoids et obésité : comprendre et agir", "sante"),
    "/sante/bien-manger-au-quotidien/": ("Bien manger au quotidien : les repères simples", "sante"),
    "/sante/manger-avant-apres-le-sport/": ("Que manger avant et après le sport ?", "sante"),
    "/sante/complements-alimentaires/": ("Compléments alimentaires : utiles ou pas ?", "sante"),
    "/sante/fatigue-stress-sommeil/": ("Fatigue, stress, ronflements : retrouver un bon sommeil", "sante"),
    "/sante/hoquet/": ("Le hoquet : pourquoi il survient et comment l'arrêter", "sante"),
    "/sante/lupus/": ("Le lupus : comprendre la maladie", "sante"),
    # Beauté & mode
    "/beaute/etre-belle-naturellement/": ("Être belle naturellement : routine et bons gestes", "beaute"),
    "/beaute/maquillage-les-bases/": ("Le maquillage : les bases pour se mettre en valeur", "beaute"),
    "/beaute/beaute-selon-les-occasions/": ("Être belle selon les occasions : plage, soirée, photo…", "beaute"),
    "/beaute/confiance-et-image-de-soi/": ("Image de soi : s'accepter et se plaire", "beaute"),
    "/beaute/mode-petit-prix/": ("Mode : bien s'habiller à petit prix", "beaute"),
    # Argent
    "/argent/rachat-de-credit/": ("Rachat de crédit : le guide complet", "argent"),
    "/argent/rachat-de-credit-conditions/": ("Rachat de crédit : conditions, dossier et taux", "argent"),
    "/argent/rachat-de-credit-selon-profil/": ("Rachat de crédit selon votre situation", "argent"),
    "/argent/credit-entre-particuliers/": ("Crédit entre particuliers : fonctionnement et précautions", "argent"),
    "/argent/surendettement/": ("Surendettement : les solutions et la procédure", "argent"),
    "/argent/banque-assurance-impots/": ("Banque en ligne, assurance auto, aides et impôts", "argent"),
    "/argent/emploi-et-travail/": ("Chômage, auto-entreprise, télétravail : vos options", "argent"),
}

# ── Pages gardées telles quelles (optique / audition) ─────────────────────
ASIS_EXTRA = {"biomedics-55-evolution.php", "buy-glasses-online.php", "lentilles-de-contact-en-ligne.php",
              "leader-optique.html"}
OPTIQUE_RX = r"optic|optique|opticien|lunette|audit|acouph|audioproth|lentille|chateau-de-nieuil"

# ── Affectations explicites (hors minceur) ────────────────────────────────
EXPLICITE = {}
def _a(cible, *noms):
    for n in noms:
        EXPLICITE[n] = cible

_a("/beaute/mode-petit-prix/", "laver-un-pull-en-cachemire-sans-l-abimer.php", "le-rouge-tendance-du-moment-de-la-mode-en-hiver.php",
   "les-collants-blancs-mode-2024.php", "louer-ses-vetements.php", "paraitre-classe-avec-des-habits-pas-cher.php",
   "robe-d-hiver-2023-a-moins-de-100-euros.php", "porter-une-robe-avec-des-bottines-pour-etre-belle.php")
_a("/beaute/maquillage-les-bases/", "comment-etre-belle-avec-du-maquillage.php", "comment-se-maquiller-pour-etre-belle.php",
   "comment-etre-belle-avec-des-boutons.php", "conseils-beautes-des-influenceuses.php")
_a("/beaute/beaute-selon-les-occasions/", "astuce-beaute-comment-etre-belle-en-hiver.php", "comment-etre-belle-a-la-piscine.php",
   "comment-etre-belle-a-la-plage.php", "comment-etre-belle-ado.php", "comment-etre-belle-au-college.php",
   "comment-etre-belle-automne-2024.php", "comment-etre-belle-en-maillot-de-bain.php", "comment-etre-belle-en-soiree.php",
   "comment-etre-belle-enceinte.php", "comment-etre-belle-le-jour-de-la-rentree.php", "comment-etre-belle-pour-une-soiree.php",
   "comment-etre-belle-sur-photo-d'identite.php", "comment-etre-belle-sur-une-photo-de-classe.php",
   "comment-etre-la-plus-belle-du-lycee.php", "faut-il-etre-belle-pour-etre-hotesse-de-l'air.php",
   "comment-etre-belle-pour-son-crush.php", "comment-etre-belle-pour-son-homme.php", "comment-etre-belle-pour-son-mari.php")
_a("/beaute/confiance-et-image-de-soi/", "comment-etre-belle-quand-on-est-moche.php", "comment-etre-belle-quand-on-est-ronde.php",
   "comment-etre-la-plus-belle.php", "accepter-ses-rondeurs.php", "alerte-grossophobie.php", "les-rides-deviennent-a-la-mode.php",
   "paraitre-plus-jeune-de-10-ans.php", "ressembler-physiquement-a-kim-kardashian.php",
   "pourquoi-cet-ete-elles-veulent-toutes-ressembler-a-nabilla.php", "il-faut-souffrir-pour-etre-belle.php",
   "pour-etre-belle-il-faut-souffrir.php", "comment-etre-belle-et-attirante.php")
_a("/sante/fatigue-stress-sommeil/", "fatigue.php", "stress.php", "ronflement.php")
_a("/sante/hoquet/", "le-hoquet.php")
_a("/sante/lupus/", "lupus.php")
_a("/sante/surpoids-et-obesite/", "surpoids-de-l-adulte.php", "scandale-des-chirurgies-bariatriques-frauduleuses.php",
   "obesite-a-lecole.php", "prevenir-obesite-chez-l-enfant.php", "comment-faire-maigrir-un-enfant.php")
_a("/sante/bien-manger-au-quotidien/", "les-bienfaits-de-la-pomme.php", "le-cafe-rend-nerveux.php", "risque-manger-trop-sucre.php",
   "manger-davant-la-tele.php", "quoi-manger-pour-couper-la-faim.php", "clous-de-girofle-dans-l-orange.php")
_a("/sante/manger-avant-apres-le-sport/", "que-manger-avant-le-sport.php", "que-manger-apres-le-sport.php")
_a("/sante/complements-alimentaires/", "quel-complement-alimentaire.php",
   "quel-est-le-meilleur-complement-alimentaire-contre-l'arthrose.php")
_a("/sante/maigrir-du-ventre/", "epice-a-privilegier-pour-avoir-un-ventre-plat.php", "quel-sport-pour-perdre-du-ventre-.php")
_a("/sante/aliments-qui-font-maigrir/", "5-fruits-a-manger-au-petit-dejeuner-pour-maigir.php")
_a("/sante/maigrir-cuisses-et-jambes/", "comment-affiner-ses-cuisses.php")
_a("/sante/maigrir-naturellement/", "perdre-du-poid-sans-se-priver.php", "pourquoi-les-stars-de-television-sont-toujours-mince.php")
_a("/sante/pourquoi-je-ne-maigris-pas/", "impact-changement-d-heure-sur-le-poids.php")
_a("/sante/regimes-et-calories/", "complement-alimentaire-bruleurs-de-graisse.php")
# Argent
_a("/argent/rachat-de-credit/", "rachat-credit.php", "rachat-de-credit.php", "objectif-rachat-de-credit.php",
   "avantages-inconvenients.php", "rachat-de-credit-moment.php", "apres-un-rachat-de-credit.php", "faq-rachat-de-credit.php",
   "interview-rachat-de-credit.php", "conseils-rachat-de-pret.php", "forum-rachat-de-credit.php", "rachat-de-credit-paris.php",
   "rachat-de-credit-2017.php", "hausse-demande-rachat-de-credit.php", "comparateur-de-rachat-de-credit.php",
   "rachat-de-credit-regroupez-prets.php", "rachat-de-credit-en-profiter.php", "mutec-shs-rachat-de-credit.php")
_a("/argent/rachat-de-credit-conditions/", "criteres-rachat-de-credit.php", "pretendre-rachat-de-credit.php",
   "qualite-dossier-rachat-de-credit.php", "scoring.php", "taux-interet-rachat-de-credit.php",
   "modifier-duree-rachat-de-credit.php", "faire-deux-rachats-de-credit.php")
_a("/argent/rachat-de-credit-selon-profil/", "rachat-de-credit-conso.php", "rachat-de-credit-immobilier.php",
   "rachat-de-pret-auto.php", "rachat-de-credit-professionnel.php", "rachat-de-credit-fonctionnaire.php",
   "rachat-de-credit-etudiant.php", "rachat-de-credit-mere-celibataire.php", "rachat-de-credit-ficp.php")
_a("/argent/credit-entre-particuliers/", "credit-entre-particulier.php", "credit-entre-particulier-ficp.php",
   "credit-particulier-locataire.php", "credit-particulier-proprietaire.php", "credit-sans-banque.php",
   "pret-particulier-sans-frais.php", "simulateur-pret-argent-particuliers.php", "serieux-et-rapide.php",
   "litige-credit-entre-particulier.php", "negocier-credit-entre-particuliers.php", "trouver-credit-entre-particulier.php")
_a("/argent/surendettement/", "surendettement.php", "dossier-de-surendettement.php", "dossier-de-surendettement-mutec-shs.php")
_a("/argent/banque-assurance-impots/", "banque-en-ligne.php", "assurance-auto.php", "loi-pinel.php", "credit-caf.php",
   "banque.html")
_a("/argent/emploi-et-travail/", "chomage.php", "auto-entrepreneur.php", "teletravail.php")

REDIRECT = {
    "index.php": "/", "dernieres-actualites.php": "/", "mentions-legales.php": "/mentions-legales/",
    "comment-etre-belle.php": "/beaute/etre-belle-naturellement/",
}
GONE = {"simulateurs-financiers-francuski.php", "banane-cavendish-menacee-par-champignon-tr4.php",
        "reponse-bien-prise-en-compte.php", "eio.php", "mlo.php", "sbjp.php", "a1.php", "en.php", "prlib.php",
        "l_annexe.php"}
TECHNIQUE_GARDE = {"touc.php", "touc1.php", "sbjp.php"}  # inclus par les pages optique : à conserver tel quel

# ── Rubriques des pages importées (gardées, nouveau design) ───────────────
IMPORT_RUB = [
    (r"bebe|bebes|elle-a-fait-un-bebe", "famille"),
    (r"piscine|spa|ph-eleve|maison-appartement|immobilier", "maison"),
    (r"billard|paris-sportifs|interview-paris|neymar|psg|sport-le-plus|rallye", "sport"),
    (r"tpmp|berdah|amir|soprano|raoult|eurovision|youtubeur|carla", "people"),
    (r"billet-avion|automne|bijou|amour|avissociete", "loisirs"),
    (r".", "actualite-archives"),
]

# ── Minceur : guide selon les mots du nom de fichier ──────────────────────
MINCEUR = [
    ("/maison/animal-en-surpoids/", r"chien|chat|cheval|lapin"),
    ("/sante/perte-de-poids-involontaire/", r"alors-que-je-mange|sans-raison|cancer|depression|d[ée]pression|manque-de-fer|plus-d.appetit|stress-fait-maigrir|hyperthyro|je-mange-donc|il-a-maigri"),
    ("/sante/prendre-du-poids/", r"prendre-du-poid|trop-maigre|je-suis-maigre|pour-etre-maigre|grosse-ou-maigre"),
    ("/sante/maigrir-du-ventre/", r"ventre"),
    ("/sante/maigrir-cuisses-et-jambes/", r"cuisse|jambe|mollet|fesse|genou|hanche"),
    ("/sante/maigrir-bras-et-visage/", r"bras|visage|joue|menton|doigt|cou\b|poitrine|seins"),
    ("/sante/que-manger-le-soir/", r"soir|d[iî]ner|nuit"),
    ("/sante/sport-et-perte-de-poids/", r"sport|v[ée]lo|courir|course|marche|corde|natation|muscu|abdo|exercice|fitness|yoga|squat|suer|aquabike|piscine|danse|elliptique|rameur|pas-faut|gainage|pilates|tennis|football|jogging|pompes|sauna|transpir|douche-froide"),
    ("/sante/maigrir-selon-age-et-profil/", r"ramadan|regles|menaupose|40-ans|50-ans|60-ans|m[ée]nopause|grossesse|enceinte|allait|homme|femme|ado|enfant|thyro|diab|pilule|st[ée]rilet|arr[eê]tant-de-fumer|fumer|apr[eè]s-"),
    ("/sante/regimes-et-calories/", r"glucide|lipide|f[ée]culent|kcal|prot[ée]ine|matiere-grasse|shaker|sauter-les-repas|produit|pharmacie|compl[ée]ment|hormone|calorie|r[ée]gime|je[uû]ne|keto|c[ée]tog|dukan|m[ée]thode|programme|plan|bicarbonate|pilule|m[ée]dicament|br[uû]leur"),
    ("/sante/pourquoi-je-ne-maigris-pas/", r"pourquoi|ne-maigri|malgr|stagn|n.arrive|sans-raison|grossi"),
    ("/sante/maigrir-vite/", r"vite|rapide|semaine|jours|mois|kilo|kg"),
    ("/sante/aliments-qui-font-maigrir/", r"fruit|l[ée]gume|aliment|cannelle|caf[ée]|th[ée]|citron|huile|graine|chocolat|courgette|eau|boisson|soupe|pomme|banane|vinaigre|gingembre|miel|riz|p[aâ]te|pain|fromage|oeuf|avocat|frite|bonbon|plat|[ée]pinard|brocoli|confiture|manger|petit-d[ée]j|sucre|pizza|alcool|bi[eè]re|vin"),
    ("/sante/maigrir-naturellement/", r"naturel|sans|facile|astuce|secret|conseil|pierre|hypno"),
]
MINCEUR_RX = r"maigr|grossi|r[ée]gime|calorie|minceur|kilo|poids|ventre-plat|cellulite|mincir|surpoids|ob[ée]s"


def plan_php():
    lignes = []
    for b in sorted(os.listdir(SRC.encode())):
        if not (b.endswith(b".php") or b.endswith(b".html")) or b"/" in b:
            continue
        if re.fullmatch(rb"20\d\d\.html", b):
            continue  # pages annuelles de l'archive, gérées avec l'archive
        nom, abime = decode_name(b)
        chemin = os.path.join(SRC.encode(), b)
        t = lire(chemin)
        ti = titre(t, nom)
        mots = len(texte(t).split())
        bas = nom.lower()
        if nom in TECHNIQUE_GARDE or nom in ASIS_EXTRA or (re.search(OPTIQUE_RX, bas) and nom not in EXPLICITE and nom not in REDIRECT):
            action, cible, rub = "asis", "", "optique"
        elif nom in GONE:
            action, cible, rub = "gone", "", ""
        elif nom in REDIRECT:
            action, cible, rub = "redirect", REDIRECT[nom], ""
        elif nom in EXPLICITE:
            action, cible, rub = "guide", EXPLICITE[nom], GUIDES[EXPLICITE[nom]][1]
        elif re.search(MINCEUR_RX, bas + " " + ti.lower()):
            cible = next((g for g, rx in MINCEUR if re.search(rx, bas)), "/sante/maigrir-les-bases/")
            action, rub = "guide", "sante"
        elif re.search(r"comment-etre-(plus-)?belle|etre-propre-et-belle", bas):
            action, cible, rub = "guide", "/beaute/etre-belle-naturellement/", "beaute"
        else:
            rub = next(r for rx, r in IMPORT_RUB if re.search(rx, bas))
            action, cible = "import", ""
        lignes.append({"ancien": "/" + nom, "fichier": chemin, "titre": ti, "mots": mots, "action": action,
                       "cible": cible, "rubrique": rub})
    return lignes


if __name__ == "__main__":
    lignes = plan_php()
    from collections import Counter
    print(Counter(l["action"] for l in lignes))
    print(Counter(l["cible"] for l in lignes if l["action"] == "guide").most_common())
    print(Counter(l["rubrique"] for l in lignes if l["action"] == "import"))
    for l in lignes:
        if l["action"] in ("import", "asis"):
            print(l["action"], l["rubrique"], l["ancien"], "|", l["titre"][:60])


def plan_archive():
    """Archive 2007-2011 : dédoublonnage (noms abîmés par le zip, titres identiques)."""
    import collections
    fichiers = []
    for racine, _, noms in os.walk(os.path.join(SRC.encode(), b"")):
        rel = os.path.relpath(racine, SRC.encode())
        if not re.match(rb"20\d\d", rel):
            continue
        for b in noms:
            if not b.endswith(b".html"):
                continue
            nom, abime = decode_name(b)
            from urllib.parse import unquote
            nom = unquote(nom)  # certains noms étaient déjà encodés (%C3%A0)
            chemin = os.path.join(racine, b)
            t = lire(chemin)
            url = "/" + rel.decode() + "/" + nom
            fichiers.append({"ancien": url, "fichier": chemin, "abime": abime, "titre": titre(t, nom),
                             "mots": len(texte(t).split()), "taille": len(t)})
    # 1) même adresse après décodage : garder la version la plus complète
    par_url = collections.defaultdict(list)
    for f in fichiers:
        par_url[f["ancien"]].append(f)
    uniques = [max(v, key=lambda f: (not f["abime"], f["mots"])) for v in par_url.values()]
    # 2) même titre (même article sous deux adresses) : une version principale, les autres redirigées
    par_titre = collections.defaultdict(list)
    for f in uniques:
        par_titre[re.sub(r"\W+", " ", f["titre"].lower()).strip()].append(f)
    lignes = []
    for groupe in par_titre.values():
        principal = max(groupe, key=lambda f: (f["mots"], len(f["ancien"])))
        rub = "archives"
        lignes.append({**principal, "action": "import", "cible": "", "rubrique": rub})
        for f in groupe:
            if f is not principal:
                lignes.append({**f, "action": "redirect", "cible": principal["ancien"], "rubrique": ""})
    return sorted(lignes, key=lambda l: l["ancien"])
