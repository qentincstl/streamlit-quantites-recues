import streamlit as st
import pandas as pd
import openai
import io
import json
import base64
from PIL import Image
import re
import fitz  # PyMuPDF

# Configuration
st.set_page_config(page_title="Lecture Quantités Reçues", layout="wide", page_icon="✅")

st.markdown("""
<h1 style="text-align:center;">✅ Lecture et Synthèse des Quantités Reçues</h1>
<style>
    .card { background:#fff; padding:1rem; border-radius:0.8rem; margin-bottom:1.2rem; box-shadow:0 2px 4px rgba(0,0,0,0.09);}
    .section-title { font-size:1.2rem; color:#005b96; margin-bottom:.5rem;}
    .debug { font-size:0.95rem; color:#888;}
</style>
""", unsafe_allow_html=True)

# Clé API
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    st.warning("⚠️ Aucune clé API détectée. Veuillez l’ajouter dans Settings > Secrets.")
    st.stop()
openai.api_key = OPENAI_API_KEY

# Prompt principal
prompt = (
    "Tu es un assistant expert en logistique et contrôle qualité.\n"
    "Tu reçois un document PDF, image ou Excel contenant un bon de livraison annoté manuellement.\n"
    "Ta mission est d’en extraire un tableau corrigé, avec les données réellement reçues.\n"
    "\n"
    "Voici exactement ce que tu dois faire :\n"
    "\n"
    "1. Pour chaque ligne du bon de livraison, identifie les informations suivantes :\n"
    "   - Référence (code article)\n"
    "   - Nom du produit\n"
    "   - Quantité indiquée initialement sur le bon de livraison\n"
    "   - Vérification manuelle (colonne à droite, typiquement '✓' ou 'X')\n"
    "   - Nouvelle quantité si elle est écrite manuellement (en cas d'erreur détectée)\n"
    "\n"
    "2. Applique la logique suivante pour chaque ligne :\n"
    "   - Si la ligne est marquée d’une coche (✓, OK, validé...) et qu’il n’y a pas de nouvelle quantité → tu gardes la quantité d’origine.\n"
    "   - Si la ligne est marquée d’une croix (✗, X, incorrect...) → alors remplace la quantité initiale par celle écrite manuellement à côté (si disponible).\n"
    "   - Si la colonne vérification est vide ou ambigüe, mentionne 'À vérifier' dans le champ 'Alerte'.\n"
    "\n"
    "3. Formate ta réponse uniquement en tableau JSON sous cette forme :\n"
    "[\n"
    "  {\"Référence\": \"1V1073DM\", \"Produit\": \"MESO MASK\", \"Quantité\": 837, \"Alerte\": \"\"},\n"
    "  {\"Référence\": \"1V1463\", \"Produit\": \"NCEF REVERSE\", \"Quantité\": 780, \"Alerte\": \"Corrigée manuellement\"},\n"
    "  {\"Référence\": \"1V1500\", \"Produit\": \"SERUM XYZ\", \"Quantité\": 0, \"Alerte\": \"À vérifier\"}\n"
    "]\n"
    "\n"
    "4. Ne commente rien autour. Réponds uniquement par ce tableau JSON propre, sans texte ni explication."
)

def extract_json_block(s: str) -> str:
    json_regex = re.compile(r'(\[.*?\])', re.DOTALL)
    matches = json_regex.findall(s)
    if not matches:
        raise ValueError("❌ Aucun bloc JSON valide trouvé.")
    return max(matches, key=len)

def call_gpt_with_image(image_data: bytes, prompt: str) -> str:
    b64 = base64.b64encode(image_data).decode()
    for attempt in range(3):
        try:
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
        except Exception as e:
            if attempt == 2:
                raise e

def process_pdf(file: bytes) -> list:
    pages_images = []
    doc = fitz.open(stream=file, filetype="pdf")
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        pages_images.append(img_bytes)
    return pages_images

def process_excel(file: bytes) -> pd.DataFrame:
    xls = pd.ExcelFile(io.BytesIO(file))
    df_all = pd.concat([xls.parse(sheet) for sheet in xls.sheet_names], ignore_index=True)
    return df_all

# Interface
st.markdown('<div class="card"><div class="section-title">1. Importez un fichier : Image, PDF ou Excel</div></div>', unsafe_allow_html=True)
uploaded = st.file_uploader("Téléverser un fichier", type=["png", "jpg", "jpeg", "pdf", "xlsx"])
if not uploaded:
    st.info("📂 Veuillez téléverser un fichier pour continuer.")
    st.stop()

# Traitement
file_bytes = uploaded.getvalue()
file_name = uploaded.name.lower()

# === PDF ou Image ===
if file_name.endswith(("pdf", "png", "jpg", "jpeg")):
    st.markdown('<div class="card"><div class="section-title">2. Analyse en cours (GPT-4o)</div>', unsafe_allow_html=True)
    all_json = []
    pages = []

    if file_name.endswith("pdf"):
        try:
            pages = process_pdf(file_bytes)
        except Exception as e:
            st.error(f"Erreur traitement PDF : {e}")
            st.stop()
    else:
        img = Image.open(io.BytesIO(file_bytes))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        pages = [buf.getvalue()]

    with st.spinner("🔍 Lecture du document en cours..."):
        for idx, page in enumerate(pages):
            st.write(f"📄 Page {idx+1}")
            try:
                raw_response = call_gpt_with_image(page, prompt)
                st.write("🧠 Réponse GPT-4o :", raw_response)
                json_str = extract_json_block(raw_response)
                data = json.loads(json_str)
                all_json.extend(data)
            except Exception as e:
                st.warning(f"⚠️ Erreur page {idx+1} : {e}")

    if not all_json:
        st.error("❌ Aucune donnée exploitable extraite.")
        st.stop()

    df = pd.DataFrame(all_json)

# === Excel ===
elif file_name.endswith("xlsx"):
    st.markdown('<div class="card"><div class="section-title">2. Lecture Excel</div>', unsafe_allow_html=True)
    try:
        df = process_excel(file_bytes)
        st.success("✅ Fichier Excel chargé avec succès.")
    except Exception as e:
        st.error(f"Erreur lecture Excel : {e}")
        st.stop()

# === Affichage résultat ===
st.markdown('<div class="card"><div class="section-title">3. Résultat et téléchargement Excel</div>', unsafe_allow_html=True)
st.dataframe(df, use_container_width=True)

out = io.BytesIO()
with pd.ExcelWriter(out, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="QUANTITES_RECUES")
out.seek(0)

st.download_button(
    "📥 Télécharger les données au format Excel",
    data=out,
    file_name="quantites_recues.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)
st.markdown('</div>', unsafe_allow_html=True)
