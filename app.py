# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import httpx
import chardet
import io
import base64
import re
import os
from PIL import Image
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import xlsxwriter

CHUNK_SIZE = 300
st.set_page_config(page_title="Verificador de Enlaces", layout="wide")

# Tipografía Aptos
st.markdown("""
<style>
html, body, [class*="css"]  {
    font-family: 'Aptos', sans-serif;
}
thead tr th {
    background-color: #f5f5f5 !important;
    color: #222 !important;
    font-weight: bold !important;
    font-size: 1.05em !important;
}
</style>
""", unsafe_allow_html=True)

def get_asset_path(filename):
    return os.path.join(os.path.dirname(__file__), filename)

def show_logo(logo_light="TRIVIA.png", logo_dark="TRIVIA_dark.png", width=180):
    try:
        img_light = Image.open(get_asset_path(logo_light))
        buffered_light = io.BytesIO()
        img_light.save(buffered_light, format="PNG")
        img_str_light = base64.b64encode(buffered_light.getvalue()).decode()

        img_dark = Image.open(get_asset_path(logo_dark))
        buffered_dark = io.BytesIO()
        img_dark.save(buffered_dark, format="PNG")
        img_str_dark = base64.b64encode(buffered_dark.getvalue()).decode()

        st.markdown(
            f'<div style="text-align:right">'
            f'<img src="data:image/png;base64,{img_str_light}" width="{width}"/>'
            f'</div>',
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.warning("No se pudo cargar el logo: " + str(e))

def detectar_codificacion(archivo):
    raw = archivo.read()
    resultado = chardet.detect(raw)
    archivo.seek(0)
    return resultado['encoding'] or 'utf-8'

def cargar_datos(uploaded_file):
    try:
        encoding = detectar_codificacion(uploaded_file)
        content = uploaded_file.read()
        decoded = content.decode(encoding, errors="replace")
        sep = "," if decoded.count(",") > decoded.count(";") else ";"
        uploaded_file.seek(0)
        return pd.read_csv(io.StringIO(decoded), sep=sep)
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        return None

def validar_url(url):
    try:
        r = httpx.get(url, timeout=10)
        if r.status_code == 200:
            return True, "OK"
        else:
            return False, f"Error {r.status_code}"
    except httpx.RequestError:
        return False, "No responde"

def analizar_enlaces(df, columna_url):
    resultados = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_url = {executor.submit(validar_url, url): (i, row) for i, (idx, row) in enumerate(df.iterrows()) for url in [row[columna_url]] if pd.notna(url)}
        for future in as_completed(future_to_url):
            i, row = future_to_url[future]
            try:
                ok, motivo = future.result()
            except Exception:
                ok, motivo = False, "Error desconocido"
            resultados.append({**row, "Estado URL": "Operativo" if ok else "No operativo", "Motivo": motivo})
    return pd.DataFrame(resultados)

def exportar_resultado(df_result):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_result.to_excel(writer, index=False, sheet_name="Resultado")
    output.seek(0)
    return output

def main():
    show_logo()
    st.title("🧪 Verificador de Enlaces TA")
    st.markdown("Sube un archivo CSV o Excel con una columna de enlaces para verificar si están operativos.")
    archivo = st.file_uploader("Cargar archivo", type=["csv", "xlsx"])
    if archivo:
        if archivo.name.endswith(".csv"):
            df = cargar_datos(archivo)
        else:
            df = pd.read_excel(archivo)
        if df is not None:
            st.success(f"Archivo cargado: {df.shape[0]} filas - {df.shape[1]} columnas")
            columna = st.selectbox("Selecciona la columna con las URLs", df.columns)
            if st.button("Verificar Enlaces"):
                with st.spinner("Verificando enlaces..."):
                    df_result = analizar_enlaces(df, columna)
                    st.success("Verificación completada.")
                    st.dataframe(df_result)
                    excel_output = exportar_resultado(df_result)
                    st.download_button("📥 Descargar resultado en Excel", data=excel_output, file_name="verificacion_enlaces.xlsx")

if __name__ == "__main__":
    main()
