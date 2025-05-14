from chat_downloader import ChatDownloader
import json

# URL del stream en vivo o VOD
url = 'https://www.twitch.tv/claudiomichaux'  # Cambia esto por el enlace real

# Archivo donde se guardarán los mensajes
output_file = 'twitch_chat2.json'

# Inicializar el descargador de chats
chat = ChatDownloader().get_chat(url)  # Esto es un generador

# Abrir el archivo de salida en modo escritura
with open(output_file, 'w', encoding='utf-8') as f:
    f.write('[\n')  # Abrimos el array JSON
    first = True
    for message in chat:
        if not first:
            f.write(',\n')  # Agrega coma entre elementos
        else:
            first = False
        json.dump(message, f, ensure_ascii=False)
    f.write('\n]')
