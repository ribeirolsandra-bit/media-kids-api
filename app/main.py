# -*- coding: utf-8 -*-
import base64
import json
import os
import re
import openai
from pathlib import Path
from typing import List
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# =====================
# CONFIG
# =====================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MOCK = os.getenv("MOCK", "false").lower() == "true"

client = openai.OpenAI(api_key=OPENAI_API_KEY)

MEDIA_ROOT = Path("media")
(MEDIA_ROOT / "images").mkdir(parents=True, exist_ok=True)

FORBIDDEN_TERMS = ["frappe", "agresse", "donne un coup", "viol", "sexe"]

app = FastAPI(title="Kids Asset API")
app.mount("/media", StaticFiles(directory="media"), name="media")

class GenerateRequest(BaseModel):
    prompt: str
    themes_possibles: List[str]

# =====================
# CORE LOGIC
# =====================

def validate_and_generate_metadata(user_prompt: str, themes_possibles: List[str]) -> dict:
    prompt_clean = user_prompt.strip()
    prompt_len = len(prompt_clean) 
    
    print(f"\n--- NOUVELLE REQUÊTE ---")
    print(f"Prompt original: {prompt_clean}")
    
    # 1️⃣ FILTRE : Taille
    if prompt_len < 3 or prompt_len > 200:
        print(f"Refus IA: FILTRE : Taille")
        return {"status": "refused", "reason": "PROMPT_SIZE_INVALID"}

    # 2️⃣ FILTRE : Anti-gibberish
    if not any(v in prompt_clean.lower() for v in "aeiouyàâéèêëîïôûùç") or re.search(r'(.)\1{4,}', prompt_clean):
        print(f"Refus IA: Anti-gibberish")
        return {"status": "refused", "reason": "PROMPT_GIBBERISH_NOT_ALLOWED"}
    
    # Mode MOCK
    if MOCK:
        return {
            "status": "approved",
            "category": "SAFE_PREVENTION",
            "theme": "other",
            "labels": {"fr": "mock", "en": "mock", "pt": "mock"},
            "tags": {"fr": ["mock"], "en": ["mock"], "pt": ["mock"]},
            "visual_description": prompt_clean
        }

    # 3️⃣ FILTRE : Mots interdits locaux
    if any(term in prompt_clean.lower() for term in FORBIDDEN_TERMS):
        print(f"Refus local: Mot interdit détecté")
        return {"status": "refused", "reason": "PROMPT_REFUSED_VIOLENCE"}

    # 4️⃣ APPEL GPT : Validation & Réinterprétation
    prompt_gpt = f"""
    Tu es un assistant pour générer des métadonnées pour des illustrations éducatives pour enfants.
    Prompt de l'utilisateur : "{prompt_clean}"
    
    MISSIONS :
    1. Analyse la cohérence : Si le prompt est une suite de mots sans lien logique ou une phrase grammaticalement impossible (ex: "bleu courir table"), utilise la catégorie 'INAPPROPRIE'. 
       La présence d’un personnage connu NE rend PAS le prompt inapproprié
    2. Catégorise le contenu (SAFE_PREVENTION, EMOTION, VIOLENCE, INAPPROPRIE).
    3. Choisis un thème parmi : {themes_possibles} obligatoire! attention pour le theme "animals" il faut que ce soit des vrais animaux si on te dit un chat muttant, chat rose met les dans le theme "character"
    4. labels doit etre une description courte (3/4 mots), tags permetteront de faire des recherches (mot clé. max 4)
    5. REINTERPRETATION OBLIGATOIRE :
   - Si le prompt contient un personnage connu, une marque ou un univers protégé,
     tu dois automatiquement le transformer en une description visuelle générique.
   - Identifie et décris précisément :
     • les couleurs dominantes
     • les formes du corps (proportions, rondeur, simplicité)
     • les éléments vestimentaires simples (sans logo ni référence)
     • les objets iconiques
     • la posture et l’émotion principale
   - N’utilise AUCUN nom de marque, de studio ou d’univers
     (Disney, Nintendo, Marvel, Pokemon, etc.). 
     La description doit permettre à un illustrateur ou une IA de recréer une image
     très proche de l’imaginaire collectif, sans enfreindre le droit d’auteur.
    
    Réponds en JSON strict :
    {{
      "category": "",
      "theme": "",
      "labels": {{ "fr": "", "en": "", "pt": "" }},
      "tags": {{ "fr": [], "en": [], "pt": [] }},
      "visual_description": "description visuelle optimisée"
    }}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt_gpt}],
        response_format={"type": "json_object"}
    )

    data = json.loads(response.choices[0].message.content)
    print(f"Prompt réinterprété par GPT: {data.get('visual_description')}")

    if data["category"] in ["VIOLENCE", "INAPPROPRIE"]:
        print(f"Refus IA: Catégorie {data['category']}")
        return {"status": "refused", "reason": "PROMPT_REFUSED_VIOLENCE"}

    data["status"] = "approved"
    return data

def generate_image(visual_description: str, theme: str) -> str:
    theme_folder = theme.lower().replace(" ", "_")
    theme_dir = MEDIA_ROOT / "images" / theme_folder
    theme_dir.mkdir(parents=True, exist_ok=True)
    
    if MOCK: return f"/media/images/other/mock.png"
    
    # Correction : On utilise visual_description ici
    real_prompt = f"""
Educational children illustration, vector style.

STYLE RULES:
- Cute children illustration
- Thick rounded dark brown outlines
- Constant outline thickness
- Soft flat colors with very light gradients
- No textures
- No shadows
- No realism
- Rounded simple shapes

CHARACTER:
- Big head
- Small body
- Simple face
- Friendly expression

SUBJECT:
{visual_description}

OUTPUT:
- Full body, Centered, Transparent background
"""    
    print(f"Envoi au moteur d'image (gpt-image-1)...")

    try:
        response = client.images.generate(
            model="gpt-image-1",
            prompt=real_prompt,
            size="auto",
            background="transparent"
        )

        image_b64 = response.data[0].b64_json
        filename = f"asset_{os.urandom(3).hex()}.png"
        filepath = theme_dir / filename

        with open(filepath, "wb") as f:
            f.write(base64.b64decode(image_b64))

        print(f"Succès ! Image enregistrée: {filename}")
        return f"/media/images/{theme_folder}/{filename}"

    except Exception as e:
        error_msg = str(e)
        print(f"ERREUR IA IMAGE: {error_msg}")
        if "safety" in error_msg.lower() or "moderation" in error_msg.lower():
            return "SAFETY_BLOCKED"
        return "ERROR"

@app.post("/generate")
def generate_asset(payload: GenerateRequest):
    print(f"1. Début validation pour: {payload.prompt}", flush=True)
    metadata = validate_and_generate_metadata(payload.prompt, payload.themes_possibles)
    print(f"DEBUG Metadata status: {metadata.get('status')}", flush=True) # <--- ICI
    
    if metadata["status"] != "approved":
        return metadata

    # Génération
    url_media = generate_image(metadata["visual_description"], metadata["theme"])
    
    # Nettoyage de la clé temporaire avant retour au Java
    del metadata["visual_description"]
    
    if url_media == "SAFETY_BLOCKED":
        return {"status": "refused", "reason": "PROMPT_REFUSED_VIOLENCE"}
    if url_media == "ERROR":
        return {"status": "refused", "reason": "TECHNICAL_ERROR"}

    metadata["url_media"] = url_media
    return metadata