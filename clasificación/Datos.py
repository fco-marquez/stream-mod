from chat_downloader import ChatDownloader
import json
import sys
import os

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python Datos.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    output_file = 'twitch_chat2.json'

    # Verificamos si el archivo ya existe
    file_exists = os.path.isfile(output_file)
    first = True

    if file_exists:
        # Reabrimos sin el último corchete de cierre
        with open(output_file, 'rb+') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                # Archivo vacío
                f.write(b'[\n')
            else:
                f.seek(-1, os.SEEK_END)
                last_char = f.read(1)
                if last_char == b']':
                    # Eliminar el corchete final
                    f.seek(-1, os.SEEK_END)
                    f.truncate()
                    f.write(b',\n')
                    first = False
    else:
        # Archivo no existe, se inicia desde cero
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('[\n')

    chat = ChatDownloader().get_chat(url)  # Generador

    try:
        with open(output_file, 'a', encoding='utf-8') as f:
            for message in chat:
                if not first:
                    f.write(',\n')
                else:
                    first = False
                json.dump(message, f, ensure_ascii=False)
    except KeyboardInterrupt:
        print("\nInterrupción detectada. Cerrando archivo correctamente...")
    finally:
        # Añadir el cierre del JSON
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write('\n]')
