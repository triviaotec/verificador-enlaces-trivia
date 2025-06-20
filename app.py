# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import httpx
import chardet
import io
import base64
import re
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
def show_logo(logo_light="TRIVIA.png", logo_dark="TRIVIA_dark.png", width=180):
    try:
        img_light = Image.open(logo_light)
        buffered_light = io.BytesIO()
        img_light.save(buffered_light, format="PNG")
        img_str_light = base64.b64encode(buffered_light.getvalue()).decode()

        img_dark = Image.open(logo_dark)
        buffered_dark = io.BytesIO()
        img_dark.save(buffered_dark, format="PNG")
        img_str_dark = base64.b64encode(buffered_dark.getvalue()).decode()

        st.markdown(
            f'''
            <style>
            .logo-switch-wrapper {{
                width: {width}px;
                max-width: 45vw;
                margin-top: 0.4em;
                margin-bottom: -1.2em;
                text-align: right;
                float: right;
                background: transparent;
            }}
            .logo-light {{ display: block; }}
            .logo-dark  {{ display: none; }}
            @media (prefers-color-scheme: dark) {{
                .logo-light {{ display: none !important; }}
                .logo-dark  {{ display: block !important; }}
            }}
            </style>
            <div class="logo-switch-wrapper">
                <img src='data:image/png;base64,{img_str_light}' class='logo-light' width='{width}px'/>
                <img src='data:image/png;base64,{img_str_dark}' class='logo-dark' width='{width}px'/>
            </div>
            ''',
            unsafe_allow_html=True
        )
    except Exception as e:
        st.warning(f"No se pudo cargar el logo: {e}")

show_logo()
st.title("Verificador de Enlaces Web – Cumplimiento Normativo")

def read_file(uploaded_file):
    raw = uploaded_file.read()
    result = chardet.detect(raw)
    encoding = result['encoding'] or 'utf-8'
    try:
        if uploaded_file.name.endswith('.csv'):
            for sep in [',', ';']:
                try:
                    df = pd.read_csv(io.BytesIO(raw), encoding=encoding, sep=sep)
                    if df.shape[1] > 1:
                        return df
                except Exception:
                    continue
        else:
            return pd.read_excel(io.BytesIO(raw))
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        return None

# MEJOR EXTRACTOR DE URLS: ¡No trunca nunca!
def extraer_url_mejorada(texto):
    if pd.isna(texto):
        return None
    # Primero, busca enlaces en HTML <a ... href="...">
    match = re.search(r"href=['\"](https?://[^\s'\"]+)['\"]", str(texto))
    if match:
        return match.group(1)
    # Busca cualquier http(s):// hasta un espacio, comilla, mayor o menor que
    match = re.search(r'(https?://[^\s\'\"<>]+)', str(texto))
    if match:
        return match.group(1)
    return None

def clasificar_url(url):
    try:
        with httpx.Client(follow_redirects=True, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/123.0.0.0 Safari/537.36",
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Referer": "https://www.portaltransparencia.cl/",
        }) as session:
            r = session.get(url)
            status = r.status_code
            final_url = r.url if hasattr(r, "url") else url

            if "portaltransparencia.cl" in url:
                ctype = r.headers.get("content-type", "")
                if "application/pdf" in ctype or "octet-stream" in ctype or "attachment" in r.headers.get("content-disposition", ""):
                    return "Enlace operativo y funcional"
                if "<html" in r.text.lower() and "acceso denegado" in r.text.lower():
                    return "Acceso prohibido"
            if status == 200:
                if hasattr(final_url, 'path'):
                    path = final_url.path.strip('/')
                else:
                    path = str(final_url).split('/', 3)[-1].strip('/')
                if path in ['', 'index.html', 'home']:
                    return "Enlace dirige al Home"
                return "Enlace operativo y funcional"
            elif status == 401:
                return "Enlace requiere autenticación de usuario"
            elif status == 403:
                return "Acceso prohibido"
            elif status == 404:
                return "Error 404 página no operativa"
            elif status >= 500:
                return "Error del servidor (5XX)"
            else:
                return f"Otro error HTTP: {status}"
    except httpx.ConnectError:
        return "No se pudo acceder: problema de DNS o red"
    except httpx.TimeoutException:
        return "Sin respuesta; probable operatividad"
    except Exception:
        return "Error desconocido"

def procesar_fila(index, row):
    url_detectada = None
    for campo in row:
        url = extraer_url_mejorada(str(campo))
        if url:
            url_detectada = url
            break
    if not url_detectada:
        return None

    motivo = clasificar_url(url_detectada)
    if motivo != "Enlace operativo y funcional":
        fila = row.to_dict()
        fila['URL detectada'] = url_detectada
        fila['Motivo de incumplimiento'] = motivo
        return fila
    return None

def mostrar_diccionario():
    st.subheader("Diccionario de resultados")
    dic = pd.DataFrame({
        "Clasificación": [
            "Enlace operativo y funcional",
            "Enlace dirige al Home",
            "Enlace requiere autenticación de usuario",
            "Acceso prohibido",
            "Error 404 página no operativa",
            "Error del servidor (5XX)",
            "Otro error HTTP",
            "Sin respuesta; probable operatividad",
            "No se pudo acceder: problema de DNS o red",
            "Error desconocido"
        ],
        "Lenguaje claro": [
            "Funciona bien y lleva al contenido.",
            "Redirige al inicio del sitio.",
            "Pide inicio de sesión.",
            "El acceso está bloqueado.",
            "La página no existe.",
            "El sitio tiene fallas internas.",
            "Ocurrió un error no identificado.",
            "No hubo respuesta, pero no falló del todo.",
            "Error técnico al resolver el dominio.",
            "No se puede identificar el problema."
        ],
        "Lenguaje técnico": [
            "HTTP 200 OK",
            "HTTP 200 pero URL final es '/' o 'index.html'",
            "HTTP 401 Unauthorized",
            "HTTP 403 Forbidden",
            "HTTP 404 Not Found",
            "HTTP 5XX",
            "Códigos 3XX-4XX no clasificados",
            "Timeout o sin status_code",
            "Error de red o DNS",
            "Excepción no controlada"
        ],
        "Lenguaje informático": [
            "response.status_code == 200",
            "final_url endswith '/' or 'index.html'",
            "response.status_code == 401",
            "response.status_code == 403",
            "response.status_code == 404",
            "response.status_code >= 500",
            "Otro status_code",
            "RequestException sin status",
            "ConnectError o DNSFailure",
            "Exception catch genérico"
        ]
    })
    st.dataframe(dic)

archivo = st.file_uploader(
    "Carga tu archivo con enlaces (CSV o Excel)",
    type=["csv", "xls", "xlsx"],
    help="Arrastra aquí tu archivo Excel o CSV. Tamaño máximo: 200 MB."
)

with st.expander("📘 Ver diccionario de resultados"):
    mostrar_diccionario()

if archivo:
    df = read_file(archivo)
    if df is not None:
        st.subheader("Síntesis del archivo cargado")
        st.markdown(f"**Nombre del archivo:** {archivo.name}")
        st.markdown(f"**Cantidad de filas:** {len(df)}")
        st.markdown(f"**Cantidad de columnas:** {len(df.columns)}")

        total_filas = len(df)
        n_chunks = (total_filas // CHUNK_SIZE) + (1 if total_filas % CHUNK_SIZE else 0)
        resultados = []
        progreso = st.progress(0)
        chunk_num = 0

        for start in range(0, total_filas, CHUNK_SIZE):
            chunk_num += 1
            end = min(start + CHUNK_SIZE, total_filas)
            df_chunk = df.iloc[start:end]
            st.info(f"Procesando bloque {chunk_num} de {n_chunks} ({end-start} filas)")
            with ThreadPoolExecutor(max_workers=20) as executor:
                tareas = {executor.submit(procesar_fila, i, row): i for i, row in df_chunk.iterrows()}
                bloque_resultados = []
                procesadas = 0
                for future in as_completed(tareas):
                    procesadas += 1
                    progreso.progress(min((start + procesadas) / total_filas, 1.0))
                    resultado = future.result()
                    if resultado:
                        bloque_resultados.append(resultado)
            resultados.extend(bloque_resultados)
            # Resumen y resultados del bloque (con estilos):
            if bloque_resultados:
                df_bloque = pd.DataFrame(bloque_resultados)
                # Reordenar columnas: Motivo de incumplimiento primero
                cols = list(df_bloque.columns)
                cols.insert(0, cols.pop(cols.index("Motivo de incumplimiento")))
                df_bloque = df_bloque[cols]
                st.markdown(
                    f"""
                    <div style='background-color:#FFF3CD; color:#856404; border-left: 6px solid #FFA726; 
                    padding: 8px 12px; margin-bottom:3px; font-weight:bold; font-size:1.01em; border-radius:7px; width: 90%;'>
                        Se detectaron <span style='color:#e65100;'>{len(df_bloque)} enlaces con incumplimiento</span> en el bloque <b>{chunk_num}</b>.
                    </div>
                    """, unsafe_allow_html=True
                )
                # FILA DE ENCABEZADOS ORIGINAL visible sobre la tabla
                st.markdown(
                    "<div style='background-color: #f5f5f5; color: #222; font-weight: bold; "
                    "padding: 6px 12px; border-radius: 6px; margin-bottom: 0.5em; font-size: 1.03em;'>"
                    + " | ".join(df_bloque.columns) +
                    "</div>",
                    unsafe_allow_html=True
                )
                st.dataframe(df_bloque)
            else:
                st.markdown(
                    f"""
                    <div style='background-color:#E0FBF3; color:#00695c; border-left: 6px solid #2EC4B6; 
                    padding: 8px 12px; margin-bottom:3px; font-weight:bold; font-size:1.01em; border-radius:7px; width: 90%;'>
                        <span style='color:#009688;'>Todos los enlaces son operativos y funcionales en el bloque <b>{chunk_num}</b>.</span>
                    </div>
                    """, unsafe_allow_html=True
                )

        # Al final, muestra/exporta todo
        if resultados:
            df_resultados = pd.DataFrame(resultados)
            encabezado_ruta = "; ".join(list(df.columns))
            df_resultados[encabezado_ruta] = df_resultados.apply(
                lambda row: "; ".join([str(row[col]) for col in df.columns]), axis=1
            )
            # Reordenar columnas: Motivo de incumplimiento primero, ruta al final
            cols = list(df_resultados.columns)
            cols.insert(0, cols.pop(cols.index("Motivo de incumplimiento")))
            if encabezado_ruta in cols:
                cols.append(cols.pop(cols.index(encabezado_ruta)))
            df_resultados = df_resultados[cols]

            # Estilo resumen final:
            st.markdown(
                f"""
                <div style='background-color:#FFF3CD; color:#856404; border-left: 6px solid #FFA726; 
                padding: 8px 12px; margin-bottom:3px; font-weight:bold; font-size:1.05em; border-radius:7px; width: 90%;'>
                    Se detectaron <span style='color:#e65100;'>{len(df_resultados)} enlaces con incumplimiento en todo el archivo</span>.
                </div>
                """, unsafe_allow_html=True
            )
            # FILA DE ENCABEZADOS ORIGINAL sobre la tabla final
            st.markdown(
                "<div style='background-color: #f5f5f5; color: #222; font-weight: bold; "
                "padding: 6px 12px; border-radius: 6px; margin-bottom: 0.5em; font-size: 1.03em;'>"
                + " | ".join(df_resultados.columns) +
                "</div>",
                unsafe_allow_html=True
            )
            st.dataframe(df_resultados)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_resultados.to_excel(writer, index=False, sheet_name='Incumplimientos')
                workbook = writer.book
                worksheet = writer.sheets['Incumplimientos']
                formato = workbook.add_format({'font_name': 'Aptos', 'font_size': 11})
                worksheet.set_column(0, df_resultados.shape[1] - 1, 25, formato)
            output.seek(0)

            b64 = base64.b64encode(output.read()).decode()
            st.markdown(f"""
                <a href="data:application/octet-stream;base64,{b64}" download="resultados_incumplimiento.xlsx">
                    📥 Descargar resultados en Excel
                </a>
            """, unsafe_allow_html=True)
        else:
            st.markdown(
                f"""
                <div style='background-color:#E0FBF3; color:#00695c; border-left: 6px solid #2EC4B6; 
                padding: 8px 12px; margin-bottom:3px; font-weight:bold; font-size:1.05em; border-radius:7px; width: 90%;'>
                    <span style='color:#009688;'>Todos los enlaces son operativos y funcionales en todo el archivo.</span>
                </div>
                """, unsafe_allow_html=True
            )
    else:
        st.error("El archivo está vacío o no se pudo procesar.")
