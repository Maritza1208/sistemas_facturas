import os
import json
import base64
from lxml import etree
from tkinter import Tk, filedialog

def cargar_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def guardar_json(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def xml_es_valido(xml_str):
    try:
        etree.fromstring(xml_str.encode('utf-8'))
        return True
    except etree.XMLSyntaxError:
        return False

def corregir_xml():
    return """<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>EjemploID</cbc:ID>
    <cbc:IssueDate>2025-03-20</cbc:IssueDate>
</AttachedDocument>"""

def procesar_cuv(cuv_path, json_path):
    cuv_data = cargar_json(cuv_path)

    errores = [
        r for r in cuv_data.get("ResultadosValidacion", [])
        if r["Clase"] == "RECHAZADO" and "Xml" in r.get("Descripcion", "")
    ]

    if errores:
        print("⚠️ Error XML detectado en CUV. Procediendo a decodificar y corregir JSON...")
        json_data = cargar_json(json_path)

        if "xmlFevFile" in json_data:
            xml_base64 = json_data["xmlFevFile"]
            try:
                xml_str = base64.b64decode(xml_base64).decode('utf-8')
                if not xml_es_valido(xml_str):
                    print("❌ XML no válido. Reemplazando por uno corregido...")
                    xml_corregido = corregir_xml()
                    nuevo_base64 = base64.b64encode(xml_corregido.encode('utf-8')).decode('utf-8')
                    json_data["xmlFevFile"] = nuevo_base64
                    guardar_json(json_data, json_path)
                    print("✅ XML corregido y JSON actualizado.")
                else:
                    print("✅ El XML ya era válido. No se hizo reemplazo.")
            except Exception as e:
                print(f"Error al decodificar XML base64: {e}")
    else:
        print("✅ No se encontraron errores de estructura XML en el CUV.")

# --------------------------
# Punto de entrada principal
# --------------------------
if __name__ == "__main__":
    Tk().withdraw()  # Oculta la ventana principal
    carpeta = filedialog.askdirectory(title="Selecciona la carpeta con los archivos JSON y CUV")

    if carpeta:
        cuv_path = os.path.join(carpeta, "archivoCUV.json")
        json_path = os.path.join(carpeta, "archivoJSON_con_xmlFevFile.json")

        if os.path.exists(cuv_path) and os.path.exists(json_path):
            procesar_cuv(cuv_path, json_path)
        else:
            print("❌ No se encontraron los archivos requeridos en la carpeta seleccionada.")
    else:
        print("⚠️ No se seleccionó ninguna carpeta.")
