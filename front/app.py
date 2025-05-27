from flask import Flask, render_template, request, Response, jsonify
import socket, threading, json, datetime, re
import requests

app = Flask(__name__)

HOST = "irc.chat.twitch.tv"
PORT = 6667
NICK = "justinfan12345"  # Anonymous
TOKEN = "oauth:"
MODERATION_API_URL = "http://localhost:7012/moderate"  # URL of the moderation service
chat_lines = []
current_channel = None
chat_thread = None
stop_event = threading.Event()
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

                    approved, reason = moderate_message(message)
                    # Always add the message, but mark it as moderated if:
                    # 1. It's not approved AND
                    # 2. Its reason is in the selected reasons
                    is_moderated = not approved and reason in selected_reasons
                    chat_lines.append({
                        "text": message,
                        "moderated": is_moderated,
                        "reason": reason if not approved else None,
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
        url = request.form.get("twitch_url")
        new_channel = url.split("/")[-1]

        # Stop existing thread if running
        if chat_thread and chat_thread.is_alive():
            stop_event.set()
            chat_thread.join()

        # Reset for new chat
        stop_event = threading.Event()
        current_channel = new_channel
        chat_thread = threading.Thread(target=connect_to_chat, args=(new_channel, stop_event), daemon=True)
        chat_thread.start()

        return render_template("index.html", channel=new_channel)

    return render_template("index.html", channel=None)

@app.route('/update_reasons', methods=['POST'])
def update_reasons():
    global selected_reasons
    data = request.get_json()
    if data and 'reasons' in data:
        selected_reasons = set(data['reasons'])
        return jsonify({"status": "success", "reasons": list(selected_reasons)})
    return jsonify({"status": "error", "message": "Invalid request"}), 400

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
