import json
import os
import sys
from collections import deque

# Mapeo de teclas a categorías
category_map = {
    '0': 'Garabatos no peyorativos',
    '1': 'Spam',
    '2': 'Racismo/Xenofobia',
    '3': 'Homofobia',
    '4': 'Contenido sexual',
    '5': 'Insulto',
    '6': 'Machismo/Misoginia/Sexismo',
    '7': 'Divulgación de información personal (doxxing)',
    '8': 'Otros',
    '9': 'Amenaza/acoso violento',
    'enter': 'No baneable'
}

# Captura de tecla sin enter
if os.name == 'nt':
    import msvcrt
    def get_key():
        key = msvcrt.getch().decode('utf-8')
        return '\n' if key == '\r' else key
else:
    import tty
    import termios
    def get_key():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            key = sys.stdin.read(1)
            return '\n' if key == '\r' else key
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

# Verificar argumento de entrada
if len(sys.argv) < 2:
    print("Error: Debes proporcionar el nombre del archivo JSON como argumento.")
    print("Uso: python script.py <archivo_entrada.json>")
    sys.exit(1)

input_file = sys.argv[1]

# Cargar mensajes como deque
with open(input_file, 'r', encoding='utf-8') as f:
    messages = deque(json.load(f))

print("Clasifica cada mensaje (teclas 0-9 para categorías, 'enter' para No baneable, ENTER para confirmar, 'd' para deshacer categoría o última asignación, 'q' para salir)\n")

history = []  # Para trackear asignaciones

while messages:
    msg = messages.popleft()
    print("\n----------------------------------")
    print(f"{msg.get('author', {}).get('name', '???')}: {msg.get('message', '')}")
    print("Clasificación → ", end='', flush=True)

    selected_categories = []
    
    while True:
        key = get_key()
        
        # Salir completamente
        if key == 'q':
            print("\nSaliendo...")
            sys.exit(0)

        # Confirmar y guardar
        elif key == '\n':
            if not selected_categories:
                selected_categories = ['enter']

            category_files = []
            for cat in selected_categories:
                cat_num = cat if cat != 'enter' else '10'
                category_name = category_map[cat]
                category_file = f'categoria_{cat_num}.json'

                if os.path.exists(category_file):
                    with open(category_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                else:
                    data = []

                data.append(msg)

                with open(category_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                category_files.append(category_file)
                if category_name == "No baneable":
                    print(f"[{category_name}] ", end='')

            history.append((msg, category_files))
            break
        # Deshacer última categoría seleccionada
        elif key == 'd':
            if selected_categories:
                removed = selected_categories.pop()
                print(f"\nCategoría removida: {category_map[removed]}")
                # Limpiar línea anterior de categorías
                print("\033[F\033[K", end='')  # Subir una línea y borrarla completamente
                print("Clasificación →", ' '.join(f"[{category_map[c]}]" for c in selected_categories), end='', flush=True)

            elif history:
                # Eliminar última asignación previa
                last_msg, last_categories = history.pop()
                for cat_file in last_categories:
                    if os.path.exists(cat_file):
                        with open(cat_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        if data and data[-1] == last_msg:
                            data.pop()
                            with open(cat_file, 'w', encoding='utf-8') as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                messages.appendleft(msg)
                messages.appendleft(last_msg)
                print("\nÚltima asignación eliminada.")
                break
            else:
                print("\nNada que deshacer.")

        # Agregar nueva categoría
        elif key in category_map and key not in selected_categories:
            selected_categories.append(key)
            print(f"[{category_map[key]}] ", end='', flush=True)

        else:
            # Tecla inválida o repetida
            continue
