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
        return '\n' if key == '\r' else key  # Normalizar Enter en Windows
else:
    import tty
    import termios
    def get_key():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            key = sys.stdin.read(1)
            return '\n' if key == '\r' else key  # Normalizar Enter en Unix
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

print("Clasifica cada mensaje (ENTER para No baneable, 'd' para eliminar última, 'q' para salir)\n")

history = []  # Para trackear asignaciones

while messages:
    msg = messages.popleft()
    
    print("\n----------------------------------")
    print(f"{msg.get('author', {}).get('name', '???')}: {msg.get('message', '')}")
    print("Clasificación → ", end='', flush=True)

    key = get_key()
    
    # Salir
    if key == 'q':
        print("\nSaliendo...")
        break
        
    # Eliminar última asignación
    elif key == 'd':
        if history:
            last_msg, last_category = history.pop()
            
            # Remover de archivo
            if os.path.exists(last_category):
                with open(last_category, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data and data[-1] == last_msg:
                    data.pop()
                    with open(last_category, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                        
                # Reinsertar mensajes
                messages.appendleft(msg)         # Mensaje actual
                messages.appendleft(last_msg)   # Mensaje desasignado
                print(f"\n\n---- Categorización eliminada: ---- \nMensaje: {last_msg.get('author', {}).get('name', '???')}: {last_msg.get('message', '')}\nCategoría: {last_category.split('_')[1][0]} - {category_map.get(last_category.split('_')[1][0], 'No baneable')}")
            else:
                print("\nError: Archivo no encontrado")
        else:
            print("\nNo hay asignaciones previas")
            messages.append(msg)
        continue
    
    # Determinar categoría
    if key in ['\n']:  # Enter
        category_number = '10'
        category_name = category_map['enter']
    elif key in category_map:
        category_number = key
        category_name = category_map[key]
    else:
        print(f"\nTecla inválida: {key}")
        messages.appendleft(msg)
        continue

    # Guardar en categoría
    category_file = f'categoria_{category_number}.json'
    
    # Cargar o crear archivo
    if os.path.exists(category_file):
        with open(category_file, 'r', encoding='utf-8') as cf:
            data = json.load(cf)
    else:
        data = []
    
    data.append(msg)
    
    # Escribir archivo
    with open(category_file, 'w', encoding='utf-8') as cf:
        json.dump(data, cf, ensure_ascii=False, indent=2)
    
    history.append((msg, category_file))
    print(f"[{category_name}]")
