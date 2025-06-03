def obtener_errores_cuv(json_data):
    errores = []
    resultados = json_data.get("ResultadosValidacion", [])
    for resultado in resultados:
        if resultado.get("Clase", "").upper() == "RECHAZADO":
            errores.append(resultado.get("Descripcion", "Error sin descripción"))
    return errores
