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
    "Voici un document contenant des calculs de quantités ou de stock (palettes, cartons, pièces, etc.). "
    "Je veux que tu :\n"
    "1. Comprennes ligne par ligne les valeurs, même si partiellement écrites\n"
    "2. Regroupes les informations logiquement par couleur ou catégorie\n"
    "3. Crées un tableau JSON clair avec : Couleur, Palettes, Cartons, Pièces, Total pièces\n"
    "4. Ne retournes que ce tableau JSON. Aucun texte autour. Pas de code Markdown.\n"
    "5. Si tu ne comprends pas, ne réponds pas ou explique l’ambiguïté en interne.\n"
    "Exemple de réponse :\n"
    "[{\"Couleur\": \"Bleu\", \"Palettes\": 2, \"Cartons\": 10, \"Pièces\": 80, \"Total pièces\": 800}]"
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
