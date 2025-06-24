import streamlit as st
import pandas as pd
import openai
import io
import json
import base64
from PIL import Image
import re

# Configuration Streamlit
st.set_page_config(page_title="Lecture Quantités Reçues", layout="wide", page_icon="✅")

st.markdown("""
<h1 style="text-align:center;">✅ Lecture et Synthèse des Quantités Reçues</h1>
<style>
    .card { background:#fff; padding:1rem; border-radius:0.8rem; margin-bottom:1.2rem; box-shadow:0 2px 4px rgba(0,0,0,0.09);}
    .section-title { font-size:1.2rem; color:#005b96; margin-bottom:.5rem;}
    .debug { font-size:0.95rem; color:#888;}
</style>
""", unsafe_allow_html=True)

# --- Clé API
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    st.warning("⚠️ Aucune clé API détectée. Veuillez l’ajouter dans Settings > Secrets.")
    st.stop()
openai.api_key = OPENAI_API_KEY

# --- Prompt
prompt = (
    "Voici une photo contenant des calculs manuels liés à des stocks (palettes, cartons, etc.). Je veux que tu :\n"
    "1. Interprètes les calculs ligne par ligne, même si l’écriture est partielle ou approximative.\n"
    "2. Identifies la structure logique : par exemple si les nombres représentent des palettes, cartons, paquets, ou pièces.\n"
    "3. Rassembles toutes les données selon les couleurs ou catégories (par exemple : blanc, bleu, rouge, etc.).\n"
    "4. Crées un tableau synthétique clair (avec colonnes comme : Couleur, Palettes, Cartons, Pièces, Total pièces).\n"
    "5. Génères un fichier Excel avec ces données pour que je puisse les exploiter facilement.\n"
    "Si des calculs semblent ambigus, précise les hypothèses que tu prends.\n"
    "Réponds UNIQUEMENT par un tableau JSON array de la forme :\n"
    "[{\"Couleur\": \"Bleu\", \"Palettes\": 2, \"Cartons\": 10, \"Pièces\": 80, \"Total pièces\": 800}]\n"
    "N’ajoute aucun texte autour, ne mets rien avant/après le JSON."
)

def extract_json_with_gpt4o(img: Image.Image, prompt: str) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]
        }],
        max_tokens=1400,
        temperature=0
    )
    return response.choices[0].message.content

def extract_json_block(s: str) -> str:
    json_regex = re.compile(r'(\[.*?\]|\{.*?\})', re.DOTALL)
    matches = json_regex.findall(s)
    if not matches:
        raise ValueError("Aucun JSON trouvé dans la sortie du modèle.")
    return max(matches, key=len)

# --- Interface
st.markdown('<div class="card"><div class="section-title">1. Importez la photo (jpeg/png) de votre feuille de calculs</div></div>', unsafe_allow_html=True)
uploaded = st.file_uploader("Sélectionnez une photo de la feuille de calculs", type=["png", "jpg", "jpeg"])
if not uploaded:
    st.info("🖼️ Veuillez importer une image pour commencer l’analyse.")
    st.stop()

file_bytes = uploaded.getvalue()
try:
    img = Image.open(io.BytesIO(file_bytes))
except Exception as e:
    st.error(f"Erreur lors du chargement de l'image : {e}")
    st.stop()

st.markdown('<div class="card"><div class="section-title">2. Aperçu de la photo</div></div>', unsafe_allow_html=True)
st.image(img, use_container_width=True)

st.markdown('<div class="card"><div class="section-title">3. Extraction du tableau</div>', unsafe_allow_html=True)
with st.spinner("🔍 Analyse de la feuille en cours..."):
    try:
        output = extract_json_with_gpt4o(img, prompt)
        st.write("🧠 Réponse brute GPT-4o :", output)
        output_clean = extract_json_block(output)
        lignes = json.loads(output_clean)
    except Exception as e:
        st.error("❌ Erreur lors de l’extraction ou du parsing JSON.")
        st.exception(e)
        st.stop()
st.markdown('</div>', unsafe_allow_html=True)

# --- Résultats
df = pd.DataFrame(lignes)
st.markdown('<div class="card"><div class="section-title">4. Résultat et téléchargement Excel</div>', unsafe_allow_html=True)
st.dataframe(df, use_container_width=True)

out = io.BytesIO()
with pd.ExcelWriter(out, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="QUANTITES_RECUES")
out.seek(0)

st.download_button(
    "📥 Télécharger le fichier Excel",
    data=out,
    file_name="quantites_recues.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)
st.markdown('</div>', unsafe_allow_html=True)
