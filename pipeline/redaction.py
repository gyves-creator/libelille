"""Rédaction de l'article par une IA gratuite (Gemini, puis Groq en secours)."""
import json
import os
import re
import time

import requests

CONSIGNES = """Tu es journaliste dans une rédaction française sérieuse et neutre.
On te donne des dépêches (titre + court résumé) publiées par plusieurs médias sur un même événement.

Ta mission : écrire un article ORIGINAL en français sur cet événement.

Règles absolues :
1. N'utilise QUE les faits présents dans les dépêches. N'invente aucun chiffre, aucune date, aucun nom, aucune citation.
   Si une information manque, ne la comble pas : reste général ou n'en parle pas.
2. Ne recopie aucune phrase des dépêches. Reformule entièrement, avec ta propre structure et ton propre angle.
3. Pas de guillemets pour citer quelqu'un, sauf si la citation exacte figure dans une dépêche (et alors 15 mots maximum).
4. Ton factuel et neutre, aucune opinion. Si les sources divergent, dis-le.
5. Ajoute du contexte général utile au lecteur (qui est la personne, de quoi parle-t-on), seulement s'il s'agit de connaissances bien établies et non datées.
6. Longueur : 350 à 550 mots. Structure : un chapeau (2 phrases), puis 3 ou 4 paragraphes, avec 1 ou 2 intertitres en markdown (## ...).

Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour :
{
  "titre": "titre informatif, 70 caractères max, sans point final",
  "chapeau": "2 phrases qui résument l'essentiel",
  "corps": "le texte en markdown (paragraphes et intertitres ##), sans répéter le titre ni le chapeau",
  "mots_cles": ["3 à 5 mots-clés"],
  "sujet_photo": "le nom propre principal à illustrer : personne, lieu, institution ou entreprise, tel qu'il s'écrit sur Wikipédia. Vide si aucun.",
  "recherche_photo": "3 à 5 mots en français décrivant une photo d'illustration générique et réaliste du sujet, sans personne célèbre (ex. : « hémicycle assemblée vote », « manifestation rue banderoles », « stade football tribunes »)"
}"""


class EchecRedaction(Exception):
    pass


def _message_utilisateur(evenement, rubrique):
    lignes = [f"Rubrique : {rubrique['nom']}", "", "Dépêches :"]
    for i, d in enumerate(evenement["depeches"][:6], 1):
        date = d["date"].strftime("%d/%m/%Y %H:%M UTC") if d["date"] else "date inconnue"
        lignes.append(f"[{i}] {d['media']} ({date})\nTitre : {d['titre']}\nRésumé : {d['resume']}\n")
    return "\n".join(lignes)


def _extraire_json(texte):
    texte = texte.strip()
    texte = re.sub(r"^```(?:json)?\s*|\s*```$", "", texte)
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut == -1 or fin == -1:
        raise ValueError("pas de JSON dans la réponse")
    return json.loads(texte[debut : fin + 1])


def _appeler_gemini_natif(fournisseur, cle, messages):
    """API Gemini native : seule route qui accepte les nouvelles clés « AQ. » de Google AI Studio."""
    systeme = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contenus = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
                for m in messages if m["role"] != "system"]
    corps = {
        "contents": contenus,
        "generationConfig": {"temperature": 0.6, "responseMimeType": "application/json"},
    }
    if systeme:
        corps["systemInstruction"] = {"parts": [{"text": systeme}]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{fournisseur['modele']}:generateContent"
    # Deux façons de passer la clé : en-tête, puis paramètre ?key= si l'en-tête est refusé.
    facons = [({"x-goog-api-key": cle}, {}), ({}, {"key": cle})]
    for tentative in range(3):
        for entete, params in facons:
            r = requests.post(url, headers={**entete, "Content-Type": "application/json"},
                              params=params, json=corps, timeout=120)
            if r.status_code not in (400, 401, 403):
                break
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(10 * (tentative + 1))
            continue
        if r.status_code >= 400:
            raise EchecRedaction(f"{fournisseur['nom']} HTTP {r.status_code} : {r.text[:200]}")
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            raise EchecRedaction(f"{fournisseur['nom']} : réponse vide ({exc})")
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
    raise EchecRedaction(f"{fournisseur['nom']} : quota atteint ou service indisponible")


def _appeler(fournisseur, messages):
    cle = os.environ.get(fournisseur["cle_env"], "").strip()
    if not cle:
        raise EchecRedaction(f"clé {fournisseur['cle_env']} absente")
    if fournisseur.get("natif"):
        return _appeler_gemini_natif(fournisseur, cle, messages)
    corps = {
        "model": fournisseur["modele"],
        "messages": messages,
        "temperature": 0.6,
        "response_format": {"type": "json_object"},
    }
    for tentative in range(3):
        r = requests.post(
            fournisseur["url"],
            headers={"Authorization": f"Bearer {cle}", "Content-Type": "application/json"},
            json=corps,
            timeout=120,
        )
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(10 * (tentative + 1))
            continue
        if r.status_code >= 400:
            raise EchecRedaction(f"{fournisseur['nom']} HTTP {r.status_code} : {r.text[:200]}")
        return r.json()["choices"][0]["message"]["content"]
    raise EchecRedaction(f"{fournisseur['nom']} : quota atteint ou service indisponible")


def _simulation(evenement, rubrique):
    """Mode test hors ligne (variable LEFIL_SIMULATION=1) : pas d'appel à une IA."""
    d = evenement["depeches"][0]
    para = (
        f"Selon les informations publiées par {len(evenement['depeches'])} source(s), {d['resume']} "
        "Ce paragraphe de démonstration remplace le texte que rédigera l'IA en production. "
    )
    return {
        "titre": d["titre"][:70],
        "chapeau": d["resume"][:200] or d["titre"],
        "corps": "\n\n".join([para * 3, "## Le contexte", para * 3, "## Et maintenant ?", para * 3]),
        "mots_cles": sorted(evenement["mots"])[:4],
        "sujet_photo": evenement.get("sujet_test", ""),
        "recherche_photo": "",
    }


def rediger(evenement, rubrique, cfg, journal=print):
    if os.environ.get("LEFIL_SIMULATION") == "1":
        return _simulation(evenement, rubrique), "simulation"

    consignes = CONSIGNES + ("\n\nRÈGLES SPÉCIFIQUES À CETTE RUBRIQUE :\n" + rubrique["consignes"] if rubrique.get("consignes") else "")
    messages = [
        {"role": "system", "content": consignes},
        {"role": "user", "content": _message_utilisateur(evenement, rubrique)},
    ]
    erreurs = []
    for f in cfg["ia"]["fournisseurs"]:
        try:
            art = _extraire_json(_appeler(f, messages))
            for champ in ("titre", "chapeau", "corps"):
                if not str(art.get(champ, "")).strip():
                    raise ValueError(f"champ « {champ} » vide")
            return art, f"{f['nom']}/{f['modele']}"
        except Exception as exc:
            journal(f"    ↳ {f['nom']} a échoué : {exc}")
            erreurs.append(str(exc))
    raise EchecRedaction(" | ".join(erreurs))
