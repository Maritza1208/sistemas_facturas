import os
import sys
import json
import pandas as pd

from controllers.procesar_excel import leer_excel
from controllers.validar_xml import obtener_errores_cuv
from controllers.corregir_xml import corregir_xml
from controllers.gestionar_archivos import (
    seleccionar_archivo_excel,
    seleccionar_carpeta,
    filtrar_archivos_por_tipo,
    leer_json,
    leer_txt
)

def main():
    print("=== Sistema de Corrección Automática de XML ===")

    # UC-1: Seleccionar archivo Excel
    ruta_excel = seleccionar_archivo_excel()
    print(f"[DEBUG] Ruta seleccionada: {ruta_excel}")

    if not ruta_excel or not os.path.exists(ruta_excel):
        print("Error: No se seleccionó un archivo válido.")
        sys.exit(1)

    facturas = leer_excel(ruta_excel)
    facturas_validas = [f for f in facturas if f and str(f).strip() != ""]

    if not facturas_validas:
        print("Error: No se encontraron números de factura válidos en el archivo Excel.")
        sys.exit(1)

    print(f"Facturas extraídas: {facturas_validas}")

    # UC-2: Seleccionar carpeta con los JSON
    ruta_carpeta = seleccionar_carpeta()
    if not ruta_carpeta or not os.path.isdir(ruta_carpeta):
        print("Error: No se seleccionó una carpeta válida.")
        sys.exit(1)

    print("Carpeta cargada con éxito.")

    archivos = os.listdir(ruta_carpeta)

    # UC-3: Procesar los JSON y corregir XML
    for archivo in archivos:
        if archivo.endswith(".json"):
            ruta_json = os.path.join(ruta_carpeta, archivo)
            try:
                with open(ruta_json, "r", encoding="utf-8") as file:
                    json_data = json.load(file)

                print(f"\nProcesando archivo: {archivo}")

                errores = obtener_errores_cuv(json_data)
                if errores:
                    print("CUV indica errores:")
                    for err in errores:
                        print(f" - {err}")
                    print("Corrigiendo XML...")

                    # Corregir XML
                    xml_corregido = corregir_xml(json_data)
                    if xml_corregido:
                        json_data["xmlFevFile"] = xml_corregido
                        with open(ruta_json, "w", encoding="utf-8") as file:
                            json.dump(json_data, file, indent=4)
                        print("XML corregido y guardado en el JSON.")
                    else:
                        print("No se pudo corregir el XML.")
                else:
                    print("No se encontraron errores en el CUV.")
            except Exception as e:
                print(f"Error al procesar {archivo}: {e}")

if __name__ == "__main__":
    main()
