import json
import sys

def extraer_mensajes(archivo_entrada, archivo_salida):
    # Leer el archivo JSON de entrada
    with open(archivo_entrada, 'r', encoding='utf-8') as f:
        datos = json.load(f)

    # Extraer solo los mensajes
    mensajes = [{"message": entrada["message"]} for entrada in datos if "message" in entrada]

    # Guardar el resultado en el archivo de salida
    with open(archivo_salida, 'w', encoding='utf-8') as f:
        json.dump(mensajes, f, ensure_ascii=False, indent=2)

# Uso: python script.py entrada.json salida.json
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python Limpiar_json.py archivo_entrada.json archivo_salida.json")
        sys.exit(1)
    archivo_entrada = sys.argv[1]
    archivo_salida = sys.argv[2]
    extraer_mensajes(archivo_entrada, archivo_salida)
