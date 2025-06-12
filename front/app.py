from flask import Flask, render_template, request, Response, jsonify
import socket, threading, json, datetime, re
import requests
import os

app = Flask(__name__)

HOST = "irc.chat.twitch.tv"
PORT = 6667
NICK = "justinfan12345"  # Anonymous
TOKEN = "oauth:"
MODERATION_API_URL = "http://localhost:7012/moderate"
MODERATED_MESSAGES_FILE = "moderated_messages.json"

chat_lines = []
current_channel = None
chat_thread = None
stop_event = threading.Event()
moderated_messages = set()  # Store moderated message IDs
selected_reasons = set([
    'Garabatos no peyorativos',
    'Spam',
    'Racismo/Xenofobia',
    'Homofobia',
    'Contenido sexual',
    'Insulto',
    'Machismo/Misoginia/Sexismo',
    'Divulgación de información personal (doxxing)',
    'Otros',
    'Amenaza/acoso violento',
    'No baneable'
])

def load_moderated_messages():
    """Load previously moderated messages from file"""
    if os.path.exists(MODERATED_MESSAGES_FILE):
        try:
            with open(MODERATED_MESSAGES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data.get('messages', []))
        except Exception as e:
            print(f"Error loading moderated messages: {e}")
    return set()

def save_moderated_message(message_id, username, text, reason):
    """Save a moderated message to the training file"""
    try:
        # Load existing data
        if os.path.exists(MODERATED_MESSAGES_FILE):
            with open(MODERATED_MESSAGES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {'messages': []}
        
        # Add new message
        data['messages'].append({
            'id': message_id,
            'username': username,
            'text': text,
            'reason': reason,
            'timestamp': datetime.datetime.now().isoformat()
        })
        
        # Save back to file
        with open(MODERATED_MESSAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"Error saving moderated message: {e}")

# Load previously moderated messages
moderated_messages = load_moderated_messages()

def moderate_message(message):
    """
    Call the moderation API to check a message
    Returns (approved, reason) tuple
    """
    try:
        response = requests.post(
            MODERATION_API_URL,
            json={"mensaje": message},
            timeout=2  # 2 second timeout
        )
        
        if response.status_code == 200:
            data = response.json()
            if data["status"] == "success":
                return data["approved"], data["reason"]
        
        # If there's any error, approve the message to avoid blocking legitimate content
        print(f"Moderation API error: {response.text}")
        return True, "appropriate"
        
    except Exception as e:
        print(f"Error calling moderation API: {str(e)}")
        return True, "appropriate"

def get_message_id(username, timestamp, text):
    """Generate a unique ID for a message"""
    return f"{username}-{timestamp}-{text}"

def connect_to_chat(channel, stop_event):
    global chat_lines
    chat_lines.clear()
    sock = socket.socket()
    sock.connect((HOST, PORT))
    sock.send(f"PASS {TOKEN}\n".encode('utf-8'))
    sock.send(f"NICK {NICK}\n".encode('utf-8'))
    sock.send(f"JOIN #{channel}\n".encode('utf-8'))

    while not stop_event.is_set():
        try:
            response = sock.recv(2048).decode('utf-8')
            if "PING" in response:
                sock.send("PONG :tmi.twitch.tv\n".encode('utf-8'))
            else:
                matches = re.search(r'^:(\w+)!.*? PRIVMSG #[\w]+ :(.+)$', response)
                if matches:
                    username = matches.group(1)
                    message = matches.group(2).strip()
                    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
                    message_id = get_message_id(username, timestamp, message)

                    # Check if message is manually moderated first
                    if message_id in moderated_messages:
                        is_moderated = True
                        reason = "Manually moderated"
                    else:
                        # If not manually moderated, check with AI
                        approved, reason = moderate_message(message)
                        is_moderated = not approved and reason in selected_reasons

                    chat_lines.append({
                        "text": message,
                        "moderated": is_moderated,
                        "reason": reason if is_moderated else None,
                        "username": username,
                        "timestamp": timestamp
                    })
        except Exception as e:
            print(f"Error in chat connection: {str(e)}")
            break

    sock.close()

@app.route('/', methods=["GET", "POST"])
def index():
    global current_channel, chat_thread, stop_event

    if request.method == "POST":
        channel = request.form.get("channel_name", "").strip().lower()
        if not channel:
            return render_template("index.html", channel=None, error="Por favor ingrese un nombre de canal")

        # Stop existing thread if running
        if chat_thread and chat_thread.is_alive():
            stop_event.set()
            chat_thread.join()

        # Reset for new chat
        stop_event = threading.Event()
        current_channel = channel
        chat_thread = threading.Thread(target=connect_to_chat, args=(channel, stop_event), daemon=True)
        chat_thread.start()

        return render_template("index.html", channel=channel)

    return render_template("index.html", channel=None)

@app.route('/channel/<channel_name>')
def channel_redirect(channel_name):
    """Handle direct channel links"""
    global current_channel, chat_thread, stop_event
    
    channel = channel_name.strip().lower()
    if not channel:
        return render_template("index.html", channel=None, error="Nombre de canal inválido")

    # Stop existing thread if running
    if chat_thread and chat_thread.is_alive():
        stop_event.set()
        chat_thread.join()

    # Reset for new chat
    stop_event = threading.Event()
    current_channel = channel
    chat_thread = threading.Thread(target=connect_to_chat, args=(channel, stop_event), daemon=True)
    chat_thread.start()

    return render_template("index.html", channel=channel)

@app.route('/update_reasons', methods=['POST'])
def update_reasons():
    global selected_reasons
    data = request.get_json()
    if data and 'reasons' in data:
        selected_reasons = set(data['reasons'])
        return jsonify({"status": "success", "reasons": list(selected_reasons)})
    return jsonify({"status": "error", "message": "Invalid request"}), 400

@app.route('/toggle_moderation', methods=['POST'])
def toggle_moderation():
    data = request.get_json()
    if not data or 'username' not in data or 'timestamp' not in data or 'text' not in data or 'reason' not in data:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
    
    message_id = get_message_id(data['username'], data['timestamp'], data['text'])
    
    if message_id in moderated_messages:
        moderated_messages.remove(message_id)
        action = "unmoderated"
    else:
        moderated_messages.add(message_id)
        save_moderated_message(message_id, data['username'], data['text'], data['reason'])
        action = "moderated"
    
    return jsonify({"status": "success", "action": action})

@app.route('/chat')
def stream_chat():
    def stream():
        prev_len = 0
        while True:
            if len(chat_lines) > prev_len:
                for msg in chat_lines[prev_len:]:
                    yield f"data: {json.dumps(msg)}\n\n"
                prev_len = len(chat_lines)
    return Response(stream(), mimetype='text/event-stream')
