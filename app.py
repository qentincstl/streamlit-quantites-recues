import streamlit as st
import openai
import io
import fitz
import base64
from PIL import Image
import json
import re
import pandas as pd

st.set_page_config(page_title="Vérification Usine - Bons Annotés", layout="wide")

st.markdown("""
<h1 style="text-align:center;">🔍 Vérification des Bons de Livraison Annotés</h1>
<style>
    .section-title { font-size:1.3rem; color:#005b96; margin-bottom:0.5rem; }
    .card { background:#fff; padding:1rem; border-radius:0.5rem;
            box-shadow:0 2px 4px rgba(0,0,0,0.07); margin-bottom:1.5rem; }
</style>
""", unsafe_allow_html=True)

# Clé API
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    st.error("🛑 Clé OpenAI manquante dans Settings > Secrets.")
    st.stop()
openai.api_key = OPENAI_API_KEY

# Prompt visuel explicite
prompt = """
Tu dois lire et interpréter l’image ci-jointe. Ce n’est pas une consigne théorique, mais une tâche visuelle.

Tu vas recevoir une image contenant un bon de livraison annoté manuellement.
Tu dois analyser VISUELLEMENT cette image pour en extraire les données réelles.

Pour chaque ligne produit visible dans l’image :
1. Lis la référence produit et le nom du produit
2. Lis la quantité corrigée (ignore les valeurs rayées, prends la valeur non rayée ou manuscrite)
3. Si la quantité est différente de la version imprimée, indique "Corrigée manuellement" dans le champ Commentaire
4. Ignore toute ligne entièrement barrée
5. Si aucune modification n’est visible, indique "OK"

Retourne uniquement un tableau JSON propre comme ceci :
[
  {
    "Référence produit / 产品参考": "REF123",
    "Nom produit": "DIA COLOR 7.1",
    "Quantité corrigée": "60",
    "Commentaire": "Corrigée manuellement"
  },
  {
    "Référence produit / 产品参考": "REF456",
    "Nom produit": "MAJIREL 5.1",
    "Quantité corrigée": "108",
    "Commentaire": "OK"
  }
]

Ne rends rien d’autre que ce JSON.
"""

def extract_json_block(s: str) -> str:
    json_regex = re.compile(r'(\[.*?\])', re.DOTALL)
    matches = json_regex.findall(s)
    if not matches:
        raise ValueError("❌ Aucun bloc JSON valide trouvé.")
    return max(matches, key=len)

def extract_image_from_pdf(file: bytes) -> list:
    doc = fitz.open(stream=file, filetype="pdf")
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        pages.append(img_bytes)
    return pages

def ask_gpt4o_with_image(image_bytes: bytes) -> list:
    b64 = base64.b64encode(image_bytes).decode()
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]
        }],
        max_tokens=1500,
        temperature=0
    )
    content = response.choices[0].message.content
    return json.loads(extract_json_block(content))

# Interface
st.markdown('<div class="card"><div class="section-title">1. Importez une image ou un PDF annoté</div></div>', unsafe_allow_html=True)
uploaded = st.file_uploader("Téléverser un fichier annoté (image ou PDF)", type=["pdf", "png", "jpg", "jpeg"])
if not uploaded:
    st.stop()

file_bytes = uploaded.getvalue()
file_name = uploaded.name.lower()

# Traitement image(s)
if file_name.endswith("pdf"):
    images = extract_image_from_pdf(file_bytes)
else:
    image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    images = [buf.getvalue()]

# Analyse
results = []
st.markdown('<div class="card"><div class="section-title">2. Lecture et interprétation</div>', unsafe_allow_html=True)
for i, image_data in enumerate(images):
    st.image(image_data, caption=f"Page {i+1}", use_container_width=True)
    with st.spinner(f"Analyse page {i+1}..."):
        try:
            result = ask_gpt4o_with_image(image_data)
            results.extend(result)
        except Exception as e:
            st.error(f"Erreur d'analyse page {i+1} : {e}")

# Affichage
if results:
    df = pd.DataFrame(results)
    st.markdown('<div class="card"><div class="section-title">3. Résultat</div>', unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True)

    # Export
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="CORRECTIONS_USINE")
    output.seek(0)

    st.download_button(
        "
