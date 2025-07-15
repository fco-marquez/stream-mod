from flask import Flask, render_template, request, Response, jsonify, make_response
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

MODERATED_MESSAGES_FILE = "/moderate_json"

def set_session_cookie(response, session_id):
    """Consistent session cookie setting"""
    response.set_cookie(
        'session_id', 
        session_id, 
        max_age=60*60*24*30,  # 30 days
        httponly=True,        # Security
        samesite='Lax'       # CSRF protection
    )

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
                print(f"Reconnected session {session_id} to existing chat for {channel_name}")
                return chat_session
            
            # Create new chat session
            chat_session = ChatSession(channel_name)
            chat_session.add_user_session(session_id)
            self.active_chats[channel_name] = chat_session
            self.user_sessions[session_id] = chat_session
            
            print(f"Created new chat session for {channel_name} with session {session_id}")
            
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
            'Garabato',
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
        self._load_chat_history()

    def _get_chat_file_path(self):
        """Get the file path for this channel's chat history"""
        return f"/tmp/chat_history_{self.channel_name}.json"
    
    def _load_chat_history(self):
        """Load chat history from file"""
        try:
            chat_file = self._get_chat_file_path()
            if os.path.exists(chat_file):
                with open(chat_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Only load recent messages (last 100 or last hour)
                    recent_messages = []
                    current_time = datetime.datetime.now()
                    
                    for msg in data.get('messages', []):
                        try:
                            # Parse timestamp to check if it's recent
                            msg_time = datetime.datetime.strptime(msg['timestamp'], '%H:%M:%S')
                            # If it's from today and within last hour, keep it
                            if len(recent_messages) < 100:  # Keep last 100 messages
                                recent_messages.append(msg)
                        except:
                            continue
                    
                    self.chat_lines = recent_messages[-100:]  # Keep last 100 messages
        except Exception as e:
            print(f"Error loading chat history for {self.channel_name}: {e}")
            self.chat_lines = []
    
    def _save_chat_history(self):
        """Save current chat history to file"""
        try:
            chat_file = self._get_chat_file_path()
            # Only save last 100 messages to avoid huge files
            messages_to_save = self.chat_lines[-100:] if len(self.chat_lines) > 100 else self.chat_lines
            
            with open(chat_file, 'w', encoding='utf-8') as f:
                json.dump({'messages': messages_to_save}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving chat history for {self.channel_name}: {e}")
    
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
        # Save chat history when stopping
        self._save_chat_history()
        if self.chat_thread and self.chat_thread.is_alive():
            self.chat_thread.join(timeout=5)
    
    def update_selected_reasons(self, reasons):
        with self.lock:
            self.selected_reasons = set(reasons)
    
    def toggle_message_moderation(self, username, timestamp, text, reason):
        message_id = get_message_id(username, timestamp, text)

        with self.lock:
            if message_id in self.moderated_messages:
                # Unmoderate
                del self.moderated_messages[message_id]
                self._persist_moderated_messages()
                action = "unmoderated"
            else:
                # Moderate
                self.moderated_messages[message_id] = {
                    "id": message_id,
                    "username": username,
                    "text": text,
                    "reason": reason,
                    "timestamp": datetime.datetime.now().isoformat()
                }
                self._persist_moderated_messages()
                action = "moderated"

        return action

    def _persist_moderated_messages(self):
        try:
            with open(MODERATED_MESSAGES_FILE, 'w', encoding='utf-8') as f:
                json.dump({'messages': list(self.moderated_messages.values())}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving moderated messages: {e}")

    
    def _connect_to_chat(self):
        sock = socket.socket()
        try:
            sock.connect((HOST, PORT))
            sock.send(f"PASS {TOKEN}\n".encode('utf-8'))
            sock.send(f"NICK {NICK}\n".encode('utf-8'))
            sock.send(f"JOIN #{self.channel_name}\n".encode('utf-8'))

            while not self.stop_event.is_set():
                try:
                    sock.settimeout(1.0)
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
                                    moderation_reasons = ["Moderado manualmente"]
                                else:
                                    # Check with AI
                                    approved, reasons = moderate_message(message)
                                    if not approved:
                                        moderation_reasons = [reason for reason in reasons if reason != "No baneable"]
                                        # Flag if at least one reason matches the selected ones
                                        is_moderated = any(r in self.selected_reasons for r in reasons)
                                    else:
                                        moderation_reasons = ["No baneable"]

                                new_message = {
                                    "text": message,
                                    "moderated": is_moderated,
                                    "reasons": moderation_reasons,
                                    "username": username,
                                    "timestamp": timestamp
                                }
                                
                                self.chat_lines.append(new_message)
                                
                                # Save to file periodically (every 10 messages)
                                if len(self.chat_lines) % 10 == 0:
                                    self._save_chat_history()
                                
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error in chat connection: {str(e)}")
                    break
        except Exception as e:
            print(f"Failed to connect to chat: {str(e)}")
        finally:
            # Save chat history when connection closes
            self._save_chat_history()
            sock.close()
# Global chat manager
chat_manager = ChatManager()

def load_moderated_messages():
    """Load previously moderated messages from file"""
    if os.path.exists(MODERATED_MESSAGES_FILE):
        try:
            with open(MODERATED_MESSAGES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                messages = data.get('messages', [])
                # Convert list -> dict by ID
                return { msg['id']: msg for msg in messages }
        except Exception as e:
            print(f"Error loading moderated messages: {e}")
    else:
        print(f"No moderated messages file found at {MODERATED_MESSAGES_FILE}")
    return {}

def save_moderated_message(message_id, username, text, reason):
    """Save or update a single moderated message"""
    try:
        # Load existing data
        if os.path.exists(MODERATED_MESSAGES_FILE):
            with open(MODERATED_MESSAGES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {'messages': []}

        # Remove any message with the same id
        data['messages'] = [msg for msg in data['messages'] if msg['id'] != message_id]

        # Add the new version
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
    """Get session ID from cookie or create new one"""
    session_id = None
    
    # Try cookie first (most reliable for page refreshes)
    session_id = request.cookies.get('session_id')
    
    # Try custom header
    if not session_id:
        session_id = request.headers.get('X-Session-ID')

    # Try URL param
    if not session_id:
        session_id = request.args.get('session_id')

    # Generate new if still missing
    if not session_id:
        session_id = str(uuid.uuid4())
        print(f"Generated new session ID: {session_id}")
    else:
        print(f"Using existing session ID: {session_id}")

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

@app.route('/stream-mod/front/', methods=["GET", "POST"])
def index():
    session_id = get_or_create_session_id(request)

    user_sessions[session_id] = {
        'last_activity': time.time(),
        'current_channel': user_sessions.get(session_id, {}).get('current_channel')
    }

    if request.method == "POST":
        channel = request.form.get("channel_name", "").strip().lower()
        if not channel:
            resp = make_response(render_template(
                "index.html",
                channel=None,
                error="Por favor ingrese un nombre de canal",
                session_id=session_id
            ))
            set_session_cookie(resp, session_id)
            return resp

        chat_manager.remove_user_session(session_id)
        chat_session = chat_manager.get_or_create_chat(channel, session_id)
        user_sessions[session_id]['current_channel'] = channel

        resp = make_response(render_template(
            "index.html",
            channel=channel,
            session_id=session_id
        ))
        set_session_cookie(resp, session_id)
        return resp

    resp = make_response(render_template(
        "index.html",
        channel=None,
        session_id=session_id
    ))
    set_session_cookie(resp, session_id)
    return resp


@app.route('/stream-mod/front/update_reasons', methods=['POST'])
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

@app.route('/stream-mod/front/filters')
def filters_stream():
    session_id = get_or_create_session_id(request)
    
    # Update session activity
    if session_id in user_sessions:
        user_sessions[session_id]['last_activity'] = time.time()
    
    chat_session = chat_manager.get_chat_for_session(session_id)
    
    if not chat_session:
        return jsonify({"status": "error", "message": "No active chat session"}), 400
    
    def stream_filters():
        last_check = time.time()
        last_filters = set()
        
        # Send current filters immediately
        with chat_session.lock:
            current_filters = list(chat_session.selected_reasons)
            last_filters = set(current_filters)
            yield f"data: {json.dumps({'type': 'filters_update', 'filters': current_filters})}\n\n"
        
        while True:
            # Check if session is still active every 30 seconds
            current_time = time.time()
            if current_time - last_check > 30:
                if not chat_session.has_active_users():
                    break
                last_check = current_time
            
            # Check for filter changes
            with chat_session.lock:
                current_filters = set(chat_session.selected_reasons)
                if current_filters != last_filters:
                    last_filters = current_filters
                    yield f"data: {json.dumps({'type': 'filters_update', 'filters': list(current_filters)})}\n\n"
            
            time.sleep(1)  # Check every second
    
    return Response(stream_filters(), mimetype='text/event-stream')


@app.route('/stream-mod/front/toggle_moderation', methods=['POST'])
def toggle_moderation():
    session_id = get_or_create_session_id(request)
    
    # Update session activity
    if session_id in user_sessions:
        user_sessions[session_id]['last_activity'] = time.time()
    
    chat_session = chat_manager.get_chat_for_session(session_id)
    
    if not chat_session:
        return jsonify({"status": "error", "message": "No active chat session"}), 400
    
    data = request.get_json()
    if not data or 'username' not in data or 'timestamp' not in data or 'text' not in data:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
    
    # Handle both single reason (backward compatibility) and multiple reasons
    reasons = None
    if 'reasons' in data:
        reasons = data['reasons']
        if not isinstance(reasons, list):
            return jsonify({"status": "error", "message": "reasons must be an array"}), 400
    elif 'reason' in data:
        # Backward compatibility - convert single reason to array
        reasons = [data['reason']] if data['reason'] else []
    
    # For moderation, we need at least one reason
    # For unmoderation, reasons can be empty/None
    if reasons is not None and len(reasons) == 0:
        # This might be an unmoderation request - check if message is currently moderated
        pass  # Let the chat_session method handle this
    
    action = chat_session.toggle_message_moderation(
        data['username'], 
        data['timestamp'], 
        data['text'], 
        reasons  # Pass the reasons array instead of single reason
    )
    
    return jsonify({"status": "success", "action": action})

@app.route('/stream-mod/front/chat')
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

@app.route('/stream-mod/front/embed-chat/<string:channel_name>')
def embed_chat(channel_name):
    session_id = get_or_create_session_id(request)
    
    # Check if we already have a session for this user
    existing_session = None
    if session_id in user_sessions:
        existing_session = user_sessions[session_id]
        existing_session['last_activity'] = time.time()
    else:
        user_sessions[session_id] = {
            "channel": channel_name,
            "last_activity": time.time()
        }

    # Always get or create chat - this will reuse existing chat if available
    chat_session = chat_manager.get_or_create_chat(channel_name, session_id)

    moderation_reason = chat_session.selected_reasons if chat_session else []

    response = make_response(render_template(
        'chat_only.html',
        channel_name=channel_name,
        moderation_reason=moderation_reason,
        chat_lines=chat_session.chat_lines,  # This will be empty on fresh start
        session_id=session_id
    ))

    # Ensure session cookie is set with proper settings
    set_session_cookie(response, session_id)

    return response


@app.before_request
def cleanup_sessions():
    """Clean up old sessions before each request"""
    cleanup_old_sessions()

if __name__ == '__main__':
    app.run(debug=True)