import json
import os
import sys

# Para captura de tecla sin enter
if os.name == 'nt':
    import msvcrt
    def get_key():
        return msvcrt.getch().decode('utf-8')
else:
    import tty
    import termios
    def get_key():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

# Archivo con los mensajes a clasificar
input_file = 'twitch_chat3.json'

# Cargar todos los mensajes
with open(input_file, 'r', encoding='utf-8') as f:
    messages = json.load(f)

print("Clasifica cada mensaje con una tecla del 0 al 9 (presiona 'q' para salir)\n")

for msg in messages:
    print("\n----------------------------------")
    print(f"{msg.get('author', {}).get('name', '???')}: {msg.get('message', '')}")
    print("Clasificación [0-9] → ", end='', flush=True)

    key = get_key()
    if key == 'q':
        print("\nSaliendo...")
        break
    if key not in '0123456789':
        print(f"\nTecla inválida: {key}")
        continue

    category_file = f'categoria_{key}.json'

    # Si ya existe el archivo, lo cargamos; si no, lo creamos nuevo
    if os.path.exists(category_file):
        with open(category_file, 'r', encoding='utf-8') as cf:
            data = json.load(cf)
    else:
        data = []

    data.append(msg)

    # Guardar el mensaje en el archivo correspondiente
    with open(category_file, 'w', encoding='utf-8') as cf:
        json.dump(data, cf, ensure_ascii=False, indent=2)

    print(f"[Guardado en categoría {key}]")
