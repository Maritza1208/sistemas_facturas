import pandas as pd

def leer_excel(ruta_excel):
    try:
        df = pd.read_excel(ruta_excel, dtype=str, header=None)  # <- SIN encabezado

        # Tomar la primera columna
        primera_columna = df.iloc[:, 0]  # todas las filas, primera columna
        facturas = primera_columna.dropna().unique().tolist()

        print(f"Se encontraron {len(facturas)} facturas en el archivo.")
        return facturas

    except Exception as e:
        print(f"Error al leer el archivo Excel: {e}")
        return []
