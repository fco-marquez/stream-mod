from flask import Flask, render_template, request, Response, jsonify
import socket, threading, json, datetime, re, uuid
import requests, os
from dotenv import load_dotenv
from collections import defaultdict
import time

# Load .env from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Determine static_url_path based on environment
if os.getenv('LOCAL'):
    static_url_path = "/stream-mod/front/static"
else:
    static_url_path = "/static"

app = Flask(
    __name__,
    static_folder="static",
    static_url_path=static_url_path
)

# Simple session storage (in production, use Redis or database)
user_sessions = {}  # session_id -> user data

HOST = "irc.chat.twitch.tv"
PORT = 6667
NICK = "justinfan12345"  # Anonymous
TOKEN = "oauth:"

if os.getenv('LOCAL'):
    MODERATION_API_URL = "http://localhost:7012/moderate"
else:
    MODERATION_API_URL = "http://gate.dcc.uchile.cl/stream-mod/ia/moderate"

MODERATED_MESSAGES_FILE = "moderated_messages.json"

# Global storage for multiple users/channels
class ChatManager:
    def __init__(self):
        self.active_chats = {}  # channel_name -> ChatSession
        self.user_sessions = {}  # session_id -> ChatSession
        self.lock = threading.Lock()
    
    def get_or_create_chat(self, channel_name, session_id):
        with self.lock:
            # Check if channel already has an active chat
            if channel_name in self.active_chats:
                chat_session = self.active_chats[channel_name]
                # Add this user session to the existing chat
                chat_session.add_user_session(session_id)
                self.user_sessions[session_id] = chat_session
                return chat_session
            
            # Create new chat session
            chat_session = ChatSession(channel_name)
            chat_session.add_user_session(session_id)
            self.active_chats[channel_name] = chat_session
            self.user_sessions[session_id] = chat_session
            
            # Start the chat thread
            chat_session.start()
            return chat_session
    
    def remove_user_session(self, session_id):
        with self.lock:
            if session_id in self.user_sessions:
                chat_session = self.user_sessions[session_id]
                chat_session.remove_user_session(session_id)
                del self.user_sessions[session_id]
                
                # If no more users, stop the chat
                if not chat_session.has_active_users():
                    chat_session.stop()
                    if chat_session.channel_name in self.active_chats:
                        del self.active_chats[chat_session.channel_name]
    
    def get_chat_for_session(self, session_id):
        return self.user_sessions.get(session_id)

class ChatSession:
    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.chat_lines = []
        self.user_sessions = set()
        self.stop_event = threading.Event()
        self.chat_thread = None
        self.lock = threading.Lock()
        self.moderated_messages = load_moderated_messages()
        self.selected_reasons = set([
            'Garabatos no peyorativos',
            'Spam',
            'Racismo/Xenofobia',
            'Homofobia',
            'Contenido sexual',
            'Insulto',
            'Machismo/Misoginia/Sexismo',
            'Divulgación de información personal (doxxing)',
            'Otros',
            'Amenaza/acoso violento'
        ])
    
    def add_user_session(self, session_id):
        with self.lock:
            self.user_sessions.add(session_id)
    
    def remove_user_session(self, session_id):
        with self.lock:
            self.user_sessions.discard(session_id)
    
    def has_active_users(self):
        with self.lock:
            return len(self.user_sessions) > 0
    
    def start(self):
        if self.chat_thread is None or not self.chat_thread.is_alive():
            self.chat_thread = threading.Thread(
                target=self._connect_to_chat, 
                daemon=True
            )
            self.chat_thread.start()
    
    def stop(self):
        self.stop_event.set()
        if self.chat_thread and self.chat_thread.is_alive():
            self.chat_thread.join(timeout=5)
    
    def update_selected_reasons(self, reasons):
        with self.lock:
            self.selected_reasons = set(reasons)
    
    def toggle_message_moderation(self, username, timestamp, text, reason):
        message_id = get_message_id(username, timestamp, text)
        
        with self.lock:
            if message_id in self.moderated_messages:
                self.moderated_messages.remove(message_id)
                action = "unmoderated"
            else:
                self.moderated_messages.add(message_id)
                save_moderated_message(message_id, username, text, reason)
                action = "moderated"
        
        return action
    
    def _connect_to_chat(self):
        sock = socket.socket()
        try:
            sock.connect((HOST, PORT))
            sock.send(f"PASS {TOKEN}\n".encode('utf-8'))
            sock.send(f"NICK {NICK}\n".encode('utf-8'))
            sock.send(f"JOIN #{self.channel_name}\n".encode('utf-8'))

            while not self.stop_event.is_set():
                try:
                    sock.settimeout(1.0)  # Allow periodic checking of stop_event
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

                            # Default values
                            is_moderated = False
                            moderation_reasons = []

                            # Check if message is manually moderated
                            with self.lock:
                                if message_id in self.moderated_messages:
                                    is_moderated = True
                                    moderation_reasons = ["Manually moderated"]
                                else:
                                    # Check with AI
                                    approved, reasons = moderate_message(message)
                                    moderation_reasons = reasons
                                    if not approved:
                                        # Flag if at least one reason matches the selected ones
                                        is_moderated = any(r in self.selected_reasons for r in reasons)

                                self.chat_lines.append({
                                    "text": message,
                                    "moderated": is_moderated,
                                    "reason": moderation_reasons if is_moderated else None,
                                    "reasons": moderation_reasons,  # Always include all reasons
                                    "username": username,
                                    "timestamp": timestamp
                                })
                                
                except socket.timeout:
                    continue  # Continue checking stop_event
                except Exception as e:
                    print(f"Error in chat connection: {str(e)}")
                    break
        except Exception as e:
            print(f"Failed to connect to chat: {str(e)}")
        finally:
            sock.close()

# Global chat manager
chat_manager = ChatManager()

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

def moderate_message(message):
    """
    Call the moderation API to check a message.
    Returns (approved: bool, reasons: list[str])
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
                # Handle both single reason and multi-label reasons
                reasons = data.get("reasons", [])
                if not reasons and "reason" in data:
                    # Fallback for single reason format
                    reasons = [data["reason"]]
                elif not reasons:
                    reasons = ["No baneable"]
                
                return data["approved"], reasons
        
        # If there's any error, approve the message
        print(f"Moderation API error: {response.text}")
        return True, ["appropriate"]
        
    except Exception as e:
        print(f"Error calling moderation API: {str(e)}")
        return True, ["appropriate"]

def get_message_id(username, timestamp, text):
    """Generate a unique ID for a message"""
    return f"{username}-{timestamp}-{text}"

def get_or_create_session_id(request):
    """Get or create session ID from request headers or generate new one"""
    # Try to get session ID from custom header first
    session_id = request.headers.get('X-Session-ID')
    
    # If not found, try to get from query parameters
    if not session_id:
        session_id = request.args.get('session_id')
    
    # If still not found, generate a new one
    if not session_id:
        session_id = str(uuid.uuid4())
        
    return session_id

def cleanup_old_sessions():
    """Clean up sessions older than 1 hour"""
    current_time = time.time()
    expired_sessions = []
    
    for session_id, session_data in user_sessions.items():
        if current_time - session_data.get('last_activity', 0) > 3600:  # 1 hour
            expired_sessions.append(session_id)
    
    for session_id in expired_sessions:
        chat_manager.remove_user_session(session_id)
        if session_id in user_sessions:
            del user_sessions[session_id]

@app.route('/', methods=["GET", "POST"])
def index():
    session_id = get_or_create_session_id(request)
    
    # Update session activity
    user_sessions[session_id] = {
        'last_activity': time.time(),
        'current_channel': user_sessions.get(session_id, {}).get('current_channel')
    }
    
    if request.method == "POST":
        channel = request.form.get("channel_name", "").strip().lower()
        if not channel:
            return render_template("index.html", channel=None, error="Por favor ingrese un nombre de canal", session_id=session_id)

        # Remove user from any existing chat
        chat_manager.remove_user_session(session_id)
        
        # Join new channel
        chat_session = chat_manager.get_or_create_chat(channel, session_id)
        user_sessions[session_id]['current_channel'] = channel

        return render_template("index.html", channel=channel, session_id=session_id)

    return render_template("index.html", channel=None, session_id=session_id)

@app.route('/channel/<channel_name>')
def channel_redirect(channel_name):
    """Handle direct channel links"""
    session_id = get_or_create_session_id(request)
    
    # Update session activity
    user_sessions[session_id] = {
        'last_activity': time.time(),
        'current_channel': channel_name
    }
    
    channel = channel_name.strip().lower()
    if not channel:
        return render_template("index.html", channel=None, error="Nombre de canal inválido", session_id=session_id)

    # Remove user from any existing chat
    chat_manager.remove_user_session(session_id)
    
    # Join new channel
    chat_session = chat_manager.get_or_create_chat(channel, session_id)
    user_sessions[session_id]['current_channel'] = channel

    return render_template("index.html", channel=channel, session_id=session_id)

@app.route('/update_reasons', methods=['POST'])
def update_reasons():
    session_id = get_or_create_session_id(request)
    
    # Update session activity
    if session_id in user_sessions:
        user_sessions[session_id]['last_activity'] = time.time()
    
    chat_session = chat_manager.get_chat_for_session(session_id)
    
    if not chat_session:
        return jsonify({"status": "error", "message": "No active chat session"}), 400
    
    data = request.get_json()
    if data and 'reasons' in data:
        chat_session.update_selected_reasons(data['reasons'])
        return jsonify({"status": "success", "reasons": list(chat_session.selected_reasons)})
    
    return jsonify({"status": "error", "message": "Invalid request"}), 400

@app.route('/toggle_moderation', methods=['POST'])
def toggle_moderation():
    session_id = get_or_create_session_id(request)
    
    # Update session activity
    if session_id in user_sessions:
        user_sessions[session_id]['last_activity'] = time.time()
    
    chat_session = chat_manager.get_chat_for_session(session_id)
    
    if not chat_session:
        return jsonify({"status": "error", "message": "No active chat session"}), 400
    
    data = request.get_json()
    if not data or 'username' not in data or 'timestamp' not in data or 'text' not in data or 'reason' not in data:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
    
    action = chat_session.toggle_message_moderation(
        data['username'], 
        data['timestamp'], 
        data['text'], 
        data['reason']
    )
    
    return jsonify({"status": "success", "action": action})

@app.route('/chat')
def stream_chat():
    session_id = get_or_create_session_id(request)
    
    # Update session activity
    if session_id in user_sessions:
        user_sessions[session_id]['last_activity'] = time.time()
    
    chat_session = chat_manager.get_chat_for_session(session_id)
    
    if not chat_session:
        return jsonify({"status": "error", "message": "No active chat session"}), 400
    
    def stream():
        prev_len = 0
        last_check = time.time()
        
        while True:
            # Check if session is still active every 30 seconds
            current_time = time.time()
            if current_time - last_check > 30:
                if not chat_session.has_active_users():
                    break
                last_check = current_time
            
            with chat_session.lock:
                if len(chat_session.chat_lines) > prev_len:
                    for msg in chat_session.chat_lines[prev_len:]:
                        yield f"data: {json.dumps(msg)}\n\n"
                    prev_len = len(chat_session.chat_lines)
            
            time.sleep(0.1)  # Small delay to prevent busy waiting
    
    return Response(stream(), mimetype='text/event-stream')

@app.route('/embed-chat/<string:channel_name>')
def embed_chat(channel_name):
    session_id = get_or_create_session_id(request)
    return render_template('chat_only.html', channel_name=channel_name, session_id=session_id)

@app.before_request
def cleanup_sessions():
    """Clean up old sessions before each request"""
    cleanup_old_sessions()

if __name__ == '__main__':
    app.run(debug=True)