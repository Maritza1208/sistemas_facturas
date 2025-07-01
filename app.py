from flask import Flask, request, render_template, redirect, url_for, session, jsonify, send_file
import os
import json
import pandas as pd
import io
import base64
import xml.etree.ElementTree as ET
import requests
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from lxml import etree
from docx import Document
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from docx.shared import Pt
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from flask_session import Session
from docx.shared import Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
import requests
import urllib3
import re
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ========== Configuración ==========
UPLOAD_FOLDER = "uploads"
HISTORIAL_PATH = os.path.join(UPLOAD_FOLDER, "corregidas.json")

INCOMING_FOLDER = "incoming"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INCOMING_FOLDER, exist_ok=True)

if not os.path.exists(HISTORIAL_PATH):
    with open(HISTORIAL_PATH, 'w', encoding='utf-8') as f:
        json.dump({}, f, indent=2, ensure_ascii=False)

API_LOGIN_URL = "https://172.17.100.104:9443/api/Auth/LoginSISPRO"
API_CARGA_JSON_URL = "https://172.17.100.104:9443/api/PaquetesFevRips/CargarFevRips"
API_CREDENCIALES = {
    "persona": {
        "identificacion": {
            "tipo": "CC",
            "numero": "1085301187"
        }
    },
    "clave": "HilaSistemas2024*",
    "nit": "891200240"
}

# ========== Funciones ==========

def limpiar_archivos_sin_cuv(upload_folder):
    archivos = os.listdir(upload_folder)
   
    facturas_con_cuv = set()

    # Encontrar facturas corregidas (tienen archivo _CUV_CORREGIDO.json)
    for archivo in archivos:
        if archivo.endswith("_CUV_CORREGIDO.json"):
            num_factura = archivo.split("_")[0]
            facturas_con_cuv.add(num_factura)

    # Construir lista de archivos a conservar (los de las facturas corregidas)
    archivos_a_conservar = set()
    for factura in facturas_con_cuv:
        for archivo in archivos:
            if archivo.startswith(factura + "_"):
                archivos_a_conservar.add(archivo)

    # Siempre conservar corregidas.json
    archivos_a_conservar.add("corregidas.json")

    # Eliminar todo archivo que NO esté en la lista para conservar
    for archivo in archivos:
        if archivo not in archivos_a_conservar:
            ruta_completa = os.path.join(upload_folder, archivo)
            if os.path.isfile(ruta_completa):
                os.remove(ruta_completa)
                print(f"🗑️ Archivo eliminado: {archivo}")

def limpiar_num_factura(num):
    """Elimina todo lo que no sea número del código de factura."""
    return re.sub(r"[^0-9]", "", num)


def buscar_attdoc(num_factura_limpio, carpeta_uploads):
    for archivo in os.listdir(carpeta_uploads):
        if archivo.endswith("_2_AttDoc.xml") and num_factura_limpio in archivo:
            return os.path.join(carpeta_uploads, archivo)
    return None


def corregir_json_valido(ruta_json_original, ruta_salida, uploads_path, num_factura):
    try:
        with open(ruta_json_original, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Ruta esperada del archivo AttDoc.xml
        ruta_attdoc = os.path.join(uploads_path, f"{num_factura}_2_AttDoc.xml")

        if not os.path.exists(ruta_attdoc):
            print(f"❌ No se encontró el archivo AttDoc: {ruta_attdoc}")
            return False

        # Leer el XML en binario y codificar a Base64
        with open(ruta_attdoc, "rb") as archivo_xml:
            contenido_xml = archivo_xml.read()
            contenido_base64 = base64.b64encode(contenido_xml).decode("utf-8")

        # Reemplazar el campo xmlFevFile
        data["xmlFevFile"] = contenido_base64

        # Guardar el JSON corregido
        with open(ruta_salida, "w", encoding="utf-8") as fout:
            json.dump(data, fout, indent=2, ensure_ascii=False)

        print(f"✅ JSON corregido guardado: {ruta_salida}")
        return True

    except Exception as e:
        print(f"❌ Error al corregir JSON para {num_factura}: {e}")
        return False

def validar_json_para_envio(json_data, factura_num):
    errores = []

    if "rips" not in json_data:
        errores.append("Falta el campo 'rips'.")
    else:
        rips = json_data["rips"]
        if "numFactura" not in rips:
            errores.append("Falta 'numFactura'.")
        if "usuarios" not in rips or not rips["usuarios"]:
            errores.append("'usuarios' vacío o inexistente.")

    if not json_data.get("xmlFevFile"):
        errores.append("Falta 'xmlFevFile' o está vacío.")

    if errores:
        print(f"❌ Errores en el JSON de la factura {factura_num}:")
        for error in errores:
            print(f"   - {error}")
        return False

    print(f"✅ JSON de factura {factura_num} está listo para enviar.")
    return True

def verificar_xml_base64_para_todas_las_facturas():
    corregidos = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith("_CORREGIDO.json")]

    for json_file in corregidos:
        json_path = os.path.join(UPLOAD_FOLDER, json_file)

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            num_factura = data.get("rips", {}).get("numFactura", "Sin número")
            xml_base64 = data.get("xmlFevFile", "")

            if not xml_base64:
                print(f"⚠️ Factura {num_factura}: No tiene XML codificado en Base64.")
                continue

            xml_decoded = base64.b64decode(xml_base64).decode("utf-8")
            print(f"\n🔍 XML decodificado para factura {num_factura}:")
            print(xml_decoded)
            print("-" * 80)

        except Exception as e:
            print(f"❌ Error procesando {json_file}: {e}")

def cargar_historial():
    """
    Carga el historial de corregidas.json, filtra entradas cuyo
    archivo corregido ya no existe, y vuelve a guardar si hubo cambios.
    """
    try:
        with open(HISTORIAL_PATH, 'r', encoding='utf-8') as f:
            historial = json.load(f)
    except Exception:
        historial = {}

    # historial es dict: factura_num → {fecha, observacion}
    entradas_originales = set(historial.keys())
    entradas_validas = {}

    for num, info in historial.items():
        nombre_archivo = f"{num}_2_CUV_CORREGIDO.json"
        ruta_archivo  = os.path.join(UPLOAD_FOLDER, nombre_archivo)
        if os.path.exists(ruta_archivo):
            entradas_validas[num] = info
        else:
            print(f"⚠️ Eliminando factura {num} del historial (archivo {nombre_archivo} no encontrado)")

    # Si hubo eliminación, reescribimos el JSON para mantenerlo en disco sincronizado
    if set(entradas_validas.keys()) != entradas_originales:
        with open(HISTORIAL_PATH, 'w', encoding='utf-8') as f:
            json.dump(entradas_validas, f, indent=2, ensure_ascii=False)

    return entradas_validas

def guardar_historial(historial):
    with open(HISTORIAL_PATH, 'w', encoding='utf-8') as f:
        json.dump(historial, f, indent=2, ensure_ascii=False)

historial_corregidas = cargar_historial()

def enviar_jsons_corregidos():
    historial_corregidas = cargar_historial()
    corregidos = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('_CORREGIDO.json')]
    print(f"🔎 Facturas corregidas encontradas: {corregidos}")

    for json_file in corregidos:
        num_factura = json_file.split("_")[0]
        if num_factura in historial_corregidas:
            print(f"⏭️ Factura {num_factura} ya enviada, saltando...")
            continue

        json_path = os.path.join(UPLOAD_FOLDER, json_file)
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not validar_json_para_envio(data, data.get('rips', {}).get('numFactura', 'Sin número')):
                continue

            print(f"📡 Enviando {json_file} al Ministerio...")
            response = requests.post(API_CARGA_JSON_URL, json=data, verify=False)

            if response.status_code == 200:
                respuesta = response.json()
                if respuesta.get('ResultState'):
                    print(f"✅ {json_file}: CUV generado correctamente: {respuesta.get('CodigoUnicoValidacion')}")
                    # Agregar al historial la factura ya enviada
                    historial_corregidas.append(num_factura)
                    guardar_historial(historial_corregidas)
                else:
                    motivo = respuesta.get('ResultadosValidacion', [{}])[0].get('Descripcion', 'Desconocido')
                    print(f"❌ {json_file}: Ministerio rechazó. Motivo: {motivo}")
            else:
                print(f"❌ {json_file}: Error HTTP {response.status_code}")

        except Exception as e:
            print(f"⚠️ Error procesando {json_file}: {e}")

# ========== Inicializar Flask App ==========

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Configura Flask-Session para que guarde la session en el servidor (filesystem)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.getcwd(), 'flask_session')
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

# Inicializa Flask-Session
Session(app)
       
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Antes de cargar, limpia sólo lo obsoleto (mantiene JSON originales y corregidos)
        limpiar_archivos_sin_cuv(UPLOAD_FOLDER)

        excel = request.files.get("excel")
        carpeta_archivos = request.files.getlist("carpeta")
        if not excel or not carpeta_archivos:
            return render_template("index.html",
                                   mensaje="⚠️ Debes subir el archivo Excel y los archivos de la carpeta.")

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        excel_path = os.path.join(INCOMING_FOLDER, excel.filename)
        excel.save(excel_path)
        session['excel_path'] = excel_path
        session.modified = True

        try:
            libro = pd.read_excel(excel_path, sheet_name=None)
            facturas_excel = []
            for nombre_hoja, df_hoja in libro.items():
                if df_hoja.shape[1] < 1:
                    continue
                series = df_hoja.iloc[:, 0].dropna().astype(str).str.strip()
                facturas_excel.extend(series.tolist())
            columna_detectada = ", ".join(libro.keys())
        except Exception as e:
            return render_template("index.html",
                                   mensaje=f"Error al leer el excel: {e}")

        # Guardamos los archivos subidos en un dict
        archivo_dict = {}
        for archivo in carpeta_archivos:
            nombre = os.path.basename(archivo.filename)
            ruta = os.path.join(INCOMING_FOLDER, nombre)
            archivo.save(ruta)
            archivo_dict[nombre] = ruta

        # Cargamos historial de facturas ya corregidas
        try:
            historial = cargar_historial()  # dict: factura → {fecha, observacion}
        except Exception as e:
            historial = {}
            print(f"⚠️ Error cargando historial: {e}")

        facturas_con_error_xml = []
        facturas_con_cuv_valido = []
        facturas_con_otros_errores = []

        # ==== Aquí viene la parte modificada: inclusión de *_2_Error.json ====
        todas = set(facturas_excel)
        for nombre in archivo_dict:
            # JSON original sin CUV
            if nombre.endswith("_2.json") and "CUV_CORREGIDO" not in nombre:
                todas.add(nombre.split("_")[0])
            # JSON de error XML
            if nombre.endswith("_2_Error.json"):
                todas.add(nombre.split("_")[0])
        # =====================================================================

        for num in todas:
            # Si ya está en historial, lo marcamos como válido y saltamos
            if num in historial:
                facturas_con_cuv_valido.append({
                    "factura":     num,
                    "descripcion": "CUV generado correctamente (registro previo)",
                    "observacion": historial[num]["observacion"]
                })
                continue

            # Procesamos posibles errores o validaciones
            ruta_error = archivo_dict.get(f"{num}_2_Error.json")
            if ruta_error and os.path.exists(ruta_error):
                try:
                    with open(ruta_error, encoding="utf-8") as f:
                        data = json.load(f)
                    rs = data.get("ResultState", False)
                    rv = data.get("ResultadosValidacion", [])
                except Exception as e:
                    facturas_con_otros_errores.append({
                        "factura": num,
                        "descripcion": "Error leyendo archivo JSON",
                        "observacion": str(e)
                    })
                    continue

                    # 1) Detectar error CFR006
                cfr = next((r for r in rv if r.get("Codigo") == "CFR006"), None)
                if cfr:
                    facturas_con_error_xml.append({
                        "factura":     num,
                        "descripcion": cfr.get("Descripcion", ""),
                        "observacion": cfr.get("Observaciones", "")
                    })
                # 2) Detectar errores de XML con [AttachedDocument]
                elif any(r.get("Clase") == "RECHAZADO" and "[AttachedDocument]" in r.get("Descripcion", "") for r in rv):
                    detail = next(r for r in rv if "[AttachedDocument]" in r.get("Descripcion", ""))
                    facturas_con_error_xml.append({
                        "factura":     num,
                        "descripcion": detail.get("Descripcion", ""),
                        "observacion": detail.get("Observaciones", "")
                    })
                # 3) Otros rechazos
                else:
                    first = rv[0]
                    facturas_con_otros_errores.append({
                        "factura":     num,
                        "descripcion": first.get("Descripcion", ""),
                        "observacion": first.get("Observaciones", "")
                    })

            else:
                # Si no existe JSON de error, revisamos el JSON normal
                ruta_normal = archivo_dict.get(f"{num}_2.json")
                if ruta_normal and os.path.exists(ruta_normal):
                    # Suponemos que está válido: lo marcamos como CUV válido pendiente de corrección automática
                    facturas_con_cuv_valido.append({
                        "factura":     num,
                        "descripcion": "JSON válido (por corregir)",
                        "observacion": "Pendiente de corrección"
                    })
                else:
                    facturas_con_otros_errores.append({
                        "factura":     num,
                        "descripcion": "No se encontró archivo .json",
                        "observacion": "No aplica"
                    })

        # Filtrar facturas con error XML que ya estén en el historial
        facturas_con_error_xml = [
            f for f in facturas_con_error_xml
            if f["factura"] not in historial
        ]

        # Guardamos en sesión para mostrar en resultados
        session["columna_detectada"]         = columna_detectada
        session["facturas_con_error"]        = facturas_con_error_xml
        session["facturas_con_cuv_corregido"]= facturas_con_cuv_valido
        session["facturas_con_otros_errores"]= facturas_con_otros_errores
        session["archivos_guardados"]        = archivo_dict
        session.modified = True

        return redirect(url_for("resultados"))

    return render_template("index.html")


@app.route("/resultado")
def resultados():
    # 1) Leemos SIEMPRE el historial actualizado
    historial = cargar_historial()  # dict: factura → {fecha, observacion}

    # 2) Tomamos de sesión los tres grupos originales
    errores = session.get("facturas_con_error", [])
    cuv_previos = session.get("facturas_con_cuv_corregido", [])
    otros = session.get("facturas_con_otros_errores", [])

    # 3) Filtramos ERRORES para excluir cualquiera que esté en el historial
    facturas_con_error = [f for f in errores if f["factura"] not in historial]

    # 4) AÑADIMOS a los CUVs previos todas las facturas del historial que aún no estén
    facturas_con_cuv_corregido = []
    ya_agregadas = set()

    for f in cuv_previos:
        facturas_con_cuv_corregido.append({
            "factura": f["factura"],
            "descripcion": f.get("descripcion", "CUV generado correctamente"),
            "observacion": "CUV validado"
        })
        ya_agregadas.add(f["factura"])

    for num, info in historial.items():
        if num not in ya_agregadas:
            facturas_con_cuv_corregido.append({
                "factura": num,
                "descripcion": "CUV generado correctamente (registro previo)",
                "observacion": "CUV validado"
            })

    # 5) Renderizar plantilla HTML con los datos
    return render_template("resultados.html",
                           columna_detectada=session.get("columna_detectada", ""),
                           facturas_con_error=facturas_con_error,
                           facturas_con_cuv_corregido=facturas_con_cuv_corregido,
                           facturas_con_otros_errores=otros)


@app.route("/vista_excel") 
def vista_excel():
    historial = cargar_historial()
    corregidas = set(historial.keys())
    facturas_set = set()  # Para evitar duplicados
    facturas = []

    def clasificar_descripcion(desc):
        desc = desc.lower()
        if "cuota moderadora" in desc or "pagos moderadores" in desc:
            return "Cuota moderada"
        elif "valor reportado en los servicios" in desc:
            return "Cirugías"
        elif "xml" in desc:
            return "XML"
        else:
            return desc  # Dejar la descripción original si no encaja

    # Facturas con error
    for f in session.get("facturas_con_error", []):
        factura = f["factura"]
        if factura in facturas_set:
            continue
        facturas_set.add(factura)
        estado = "Corregida" if factura in corregidas else "No corregida"
        if estado == "Corregida":
            descripcion = "Factura válida por el Ministerio"
        else:
            descripcion = clasificar_descripcion(f["descripcion"])
        facturas.append({"factura": factura, "estado": estado, "descripcion": descripcion})

    # Facturas válidas
    for f in session.get("facturas_con_cuv_corregido", []):
        factura = f["factura"]
        if factura in facturas_set:
            continue
        facturas_set.add(factura)
        facturas.append({
            "factura": factura,
            "estado": "Válida",
            "descripcion": "Factura válida por el Ministerio"
        })

    # Otros errores
    for f in session.get("facturas_con_otros_errores", []):
        factura = f["factura"]
        if factura in facturas_set:
            continue
        facturas_set.add(factura)
        descripcion = clasificar_descripcion(f["descripcion"])
        facturas.append({
            "factura": factura,
            "estado": "Inválida",
            "descripcion": descripcion
        })

    return render_template("vista_excel.html", facturas=facturas)

@app.route("/descargar_excel_actualizado", methods=["POST"])
def descargar_excel_actualizado():
    import pandas as pd
    import io
    import os
    from flask import session, send_file

    # 1) Recuperar ruta del Excel original de la sesión
    excel_path = session.get("excel_path")
    if not excel_path or not os.path.exists(excel_path):
        return "⚠️ No encuentro el Excel original en sesión.", 400

    # 2) Volver a cargar todas las hojas
    try:
        libro = pd.read_excel(excel_path, sheet_name=None)
    except Exception as e:
        return f"❌ Error al reabrir el Excel: {e}", 500

    # 3) Diccionarios desde sesión
    errores_dict = {f["factura"]: f["descripcion"] for f in session.get("facturas_con_error", [])}
    valido_dict = {f["factura"]: f["observacion"] for f in session.get("facturas_con_cuv_corregido", [])}
    otros_dict = {f["factura"]: f["descripcion"] for f in session.get("facturas_con_otros_errores", [])}

    # 4) Clasificador de descripción
    def clasificar_descripcion(msg):
        msg_lower = msg.lower()
        if "cuotas moderadoras" in msg_lower or "pagos moderadores" in msg_lower:
            return "Cuota moderada"
        elif "valor reportado en los servicios" in msg_lower:
            return "Cirugías"
        elif "xml" in msg_lower or "attacheddocument" in msg_lower:
            return "XML"
        else:
            return msg

    # 5) Generar nuevo Excel con colores
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for hoja, df_hoja in libro.items():
            if df_hoja.shape[1] < 1:
                continue

            facs = df_hoja.iloc[:, 0].dropna().astype(str).str.strip()
            filas = []

            for fac in facs:
                if fac in errores_dict:
                    estado = "Error"
                    descripcion = clasificar_descripcion(errores_dict[fac])
                elif fac in valido_dict:
                    estado = "Válida"
                    descripcion = "Factura válida por el Ministerio"
                elif fac in otros_dict:
                    estado = "Otro error"
                    descripcion = clasificar_descripcion(otros_dict[fac])
                else:
                    estado = "No procesada"
                    descripcion = ""

                filas.append({
                    "Factura": fac,
                    "Estado": estado,
                    "Descripción": descripcion
                })

            # Crear DataFrame para esta hoja
            df_resultado = pd.DataFrame(filas)
            df_resultado.to_excel(writer, sheet_name=hoja, index=False)

            # Obtener acceso al worksheet para aplicar formato
            workbook  = writer.book
            worksheet = writer.sheets[hoja]

            # Formato verde claro para filas válidas
            formato_verde = workbook.add_format({'bg_color': "#30D651"})

            # Aplicar formato condicional fila por fila si estado == "Válida"
            for fila_idx, estado in enumerate(df_resultado["Estado"], start=1):  # +1 por el header
                if estado == "Válida":
                    worksheet.set_row(fila_idx, None, formato_verde)

    output.seek(0)
    return send_file(
        output,
        download_name="facturas_actualizadas_por_hoja.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route("/ver_reportes")
def ver_reportes():
    from datetime import datetime

    #ruta_archivo = "uploads/corregidas.json"

    # 1. Cargar datos desde el archivo JSON
    if os.path.exists(HISTORIAL_PATH):
        with open(HISTORIAL_PATH, "r", encoding="utf-8") as f:
            historial_corregidas = json.load(f)
    else:
        historial_corregidas = {}

    #corregidas = []

    # 2. Recorrer lo que está en el JSON
    facturas = []
    for factura_id, info in historial_corregidas.items():
        facturas.append({
            "factura": factura_id,
            "descripcion": "Error XML corregido",
            "observacion": info.get("observacion", "No aplica"),
            "fecha": info.get("fecha", "Fecha no registrada")
        })

    # 3. Enviar los datos al HTML
    return render_template("reportes.html", 
                           fecha=datetime.now().strftime("%Y-%m-%d %H:%M"),
                           total=len(facturas),
                           facturas=facturas
    )



# ✅ REPORTE EN PDF
from reportlab.platypus import Image

@app.route("/descargar_pdf")
def descargar_pdf():
    if os.path.exists(HISTORIAL_PATH):
        with open(HISTORIAL_PATH, "r", encoding="utf-8") as f:
            historial = json.load(f)
    else:
        historial = {}

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # 🏥 Insertar logo del hospital
    logo_path = os.path.join("static", "img", "logo.jpg")
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=120, height=50)
        logo.hAlign = 'CENTER'
        elements.append(logo)
        elements.append(Spacer(1, 10))

    # Título
    elements.append(Paragraph("📄 Reporte Histórico de Facturas Corregidas", styles['Title']))
    elements.append(Spacer(1, 12))

    # Fecha
    elements.append(Paragraph(f"<b>Fecha de generación:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 12))

    if not historial:
        elements.append(Paragraph("❌ No hay facturas corregidas en el historial.", styles['Normal']))
    else:
        data = [["Factura", "Fecha", "Observación"]]
        for num, info in historial.items():
            data.append([str(num), info.get("fecha", ""), "Error XML corregido"])

        table = Table(data, colWidths=[100, 150, 250])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#007bff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
        ]))

        elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, download_name="reporte_historico_facturas_corregidas.pdf", as_attachment=True, mimetype="application/pdf")

# ✅ REPORTE EN WORD
@app.route("/descargar_word")
def descargar_word():
    if os.path.exists(HISTORIAL_PATH):
        with open(HISTORIAL_PATH, "r", encoding="utf-8") as f:
            historial = json.load(f)
    else:
        historial = {}

    doc = Document()

    # 🏥 Insertar logo arriba del título
    logo_path = os.path.join("static", "img", "logo.jpg")
    if os.path.exists(logo_path):
        doc.add_picture(logo_path, width=Inches(2.5))  # Ajusta el tamaño
        last_paragraph = doc.paragraphs[-1]
        last_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

    # Título
    titulo = doc.add_heading("📄 Reporte Histórico de Facturas Corregidas", level=1)
    titulo.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

    # Fecha
    doc.add_paragraph(f"Fecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if not historial:
        doc.add_paragraph("❌ No hay facturas corregidas en el historial.")
    else:
        table = doc.add_table(rows=1, cols=3)
        table.style = 'Colorful List'  # Puedes probar otras
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Factura"
        hdr_cells[1].text = "Fecha"
        hdr_cells[2].text = "Observación"

        for cell in hdr_cells:
            for p in cell.paragraphs:
                p.runs[0].bold = True

        for num, info in historial.items():
            row_cells = table.add_row().cells
            row_cells[0].text = str(num)
            row_cells[1].text = info.get("fecha", "")
            row_cells[2].text = "Error XML corregido"

    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return send_file(output, download_name="reporte_historico_facturas_corregidas.docx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# Ruta para procesar las facturas con error en XML
@app.route("/corregir", methods=["POST"])
def corregir_y_enviar():
    global historial_corregidas
    try:
        print("=== INICIO CORRECCIÓN AUTOMÁTICA ===")

        # ── FILTRAR FACTURAS YA CORREGIDAS ───────────────────────────────
        historial_corregidas = cargar_historial()  # dict: factura → {fecha, observacion}
        facturas_con_error = session.get("facturas_con_error", [])
        facturas_con_error = [
            f for f in facturas_con_error
            if f["factura"] not in historial_corregidas
        ]
        # ── FIN FILTRADO ────────────────────────────────────────────────

        archivo_dict = session.get("archivos_guardados", {})
        facturas_cuv = session.get("facturas_con_cuv_corregido", [])

        if not facturas_con_error:
            print("⚠️ No hay facturas con error XML nuevas para corregir.")
            return jsonify({"mensaje": "No hay facturas con error XML."}), 400

        # --- Autenticación en API ---
        r_login = requests.post(API_LOGIN_URL, json=API_CREDENCIALES, verify=False)
        r_login.raise_for_status()
        token = r_login.json().get("token")
        if not token:
            return jsonify({"mensaje": "No se pudo autenticar con el Ministerio."}), 401
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        errores = []
        corregidas = []

        for f in facturas_con_error:
            num = f["factura"]
            print(f"\n--- Procesando factura {num} ---")

            # 1) Preparar y corregir JSON
            path_json = archivo_dict.get(f"{num}_2.json")
            ruta_salida = os.path.join(INCOMING_FOLDER, f"{num}_2_CORREGIDO.json")
            if not path_json or not os.path.exists(path_json):
                errores.append(f"{num}: JSON original no encontrado.")
                continue
            num_limpio = limpiar_num_factura(num)
            if not corregir_json_valido(path_json, ruta_salida, INCOMING_FOLDER, num_limpio):
                errores.append(f"{num}: Error al corregir el JSON.")
                continue

            # 2) Copiar corregido a uploads
            import shutil
            for nombre in os.listdir(INCOMING_FOLDER):
                if nombre.startswith(f"{num}_"):
                    shutil.copyfile(
                        os.path.join(INCOMING_FOLDER, nombre),
                        os.path.join(UPLOAD_FOLDER, nombre)
                    )

            # 3) Validar y enviar
            with open(ruta_salida, "r", encoding="utf-8") as fcor:
                json_corregido = json.load(fcor)
            if not validar_json_para_envio(json_corregido, num):
                errores.append(f"{num}: JSON inválido, no se envió.")
                continue

            print(f"📡 Enviando factura {num} corregida...")
            r = requests.post(API_CARGA_JSON_URL, headers=headers,
                              json=json_corregido, verify=False)
            res = r.json()

            # 4a) CUV existente (RVG02)
            if (not res.get("ResultState") and
                any(item.get("Codigo") == "RVG02" for item in res.get("ResultadosValidacion", []))):
                texto = next(item["Observaciones"]
                             for item in res["ResultadosValidacion"]
                             if item.get("Codigo") == "RVG02")
                m = re.search(r"CUV\s*([0-9a-f]+)", texto)
                if m:
                    cuv = m.group(1)
                    nuevo_res = {
                        **{k: v for k, v in res.items() if k != "ResultadosValidacion"},
                        "CodigoUnicoValidacion": cuv,
                        "ResultadosValidacion": [
                            i for i in res["ResultadosValidacion"]
                            if i.get("Clase") == "NOTIFICACION"
                        ]
                    }
                    #ResultState true
                    nuevo_res["ResultState"] = True
                    with open(os.path.join(UPLOAD_FOLDER, f"{num}_2_CUV_CORREGIDO.json"),
                              "w", encoding="utf-8") as f_cuv:
                        json.dump(nuevo_res, f_cuv, indent=2, ensure_ascii=False)

                    historial_corregidas[num] = {
                        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "observacion": cuv
                    }
                    corregidas.append({"factura": num, "observacion": cuv})
                    facturas_cuv.append({
                        "factura": num,
                        "descripcion": "CUV generado correctamente",
                        "observacion": cuv
                    })
                    print(f"🔄 {num}: CUV existente armado y guardado: {cuv}")
                    continue

            # 4b) CUV nuevo
            if r.status_code == 200 and res.get("ResultState"):
                cuv = res.get("CodigoUnicoValidacion", "CUV generado")
                with open(os.path.join(UPLOAD_FOLDER, f"{num}_2_CUV_CORREGIDO.json"),
                          "w", encoding="utf-8") as f_cuv:
                    json.dump(res, f_cuv, indent=2, ensure_ascii=False)

                historial_corregidas[num] = {
                    "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "observacion": cuv
                }
                corregidas.append({"factura": num, "observacion": cuv})
                facturas_cuv.append({
                    "factura": num,
                    "descripcion": "CUV generado correctamente",
                    "observacion": cuv
                })
                print(f"✅ CUV generado y guardado para {num}")
            else:
                obs = res.get("ResultadosValidacion", [{}])[0].get("Observaciones", "Error desconocido")
                errores.append(f"{num}: {obs}")
                print(f"❌ Ministerio rechazó {num}: {obs}")

        # 5) Filtrar errores y actualizar sesión
        facturas_con_error = [
            f for f in facturas_con_error
            if f["factura"] not in [c["factura"] for c in corregidas]
        ]
        session["facturas_con_error"] = facturas_con_error
        session["facturas_con_cuv_corregido"] = facturas_cuv
        session.modified = True

        # 6) Guardar historial y limpieza de archivos
        guardar_historial(historial_corregidas)
        historial_corregidas = cargar_historial()
        limpiar_archivos_sin_cuv(UPLOAD_FOLDER)

        return jsonify({
            "mensaje":   "Corrección finalizada",
            "corregidas": corregidas,
            "errores":   errores,
            "total_corregidas": len(corregidas),
            "total_no_corregidas": len(errores)
        }), 200

    except Exception as e:
        print(f"❌ ERROR GENERAL: {e}")
        return jsonify({"mensaje": "Error inesperado"}), 500

if __name__ == "__main__":
    app.run(debug=True)