import os
import json
import tkinter as tk
from tkinter import filedialog

def seleccionar_archivo_excel():
    """Abre un cuadro de diálogo para que el usuario seleccione un archivo Excel"""
    root = tk.Tk()
    root.withdraw()
    archivo = filedialog.askopenfilename(
        title="Selecciona el archivo Excel",
        filetypes=[("Archivos Excel", "*.xlsx *.xls")]
    )
    
    if archivo:
        print(f"📄 Archivo Excel seleccionado: {archivo}")
        return archivo
    else:
        print("⚠ No se seleccionó ningún archivo Excel.")
        return None

def seleccionar_carpeta():
    """Abre un cuadro de diálogo para que el usuario seleccione una carpeta"""
    root = tk.Tk()
    root.withdraw()
    carpeta = filedialog.askdirectory(title="Selecciona la carpeta de FACTURAS")
    
    if carpeta:
        print(f"📁 Carpeta seleccionada: {carpeta}")
        return carpeta
    else:
        print("⚠ No se seleccionó ninguna carpeta.")
        return None

def listar_archivos(ruta_carpeta):
    if ruta_carpeta and os.path.exists(ruta_carpeta) and os.path.isdir(ruta_carpeta):
        return os.listdir(ruta_carpeta)
    return []

def filtrar_archivos_por_tipo(ruta_carpeta, extension):
    archivos = listar_archivos(ruta_carpeta)
    return [archivo for archivo in archivos if archivo.lower().endswith(extension)]

def leer_json(ruta_carpeta, nombre_archivo):
    ruta_archivo = os.path.join(ruta_carpeta, nombre_archivo)
    try:
        with open(ruta_archivo, 'r', encoding='utf-8') as archivo:
            return json.load(archivo)
    except Exception as e:
        print(f"❌ Error al leer {nombre_archivo}: {e}")
        return None

def leer_txt(ruta_carpeta, nombre_archivo):
    ruta_archivo = os.path.join(ruta_carpeta, nombre_archivo)
    try:
        with open(ruta_archivo, 'r', encoding='utf-8') as archivo:
            return archivo.readlines()
    except Exception as e:
        print(f"❌ Error al leer {nombre_archivo}: {e}")
        return None
