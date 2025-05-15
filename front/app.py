from flask import Flask, render_template, request, Response
from moderator import moderate_message
import socket
import threading

app = Flask(__name__)

HOST = "irc.chat.twitch.tv"
PORT = 6667
NICK = "justinfan12345"  # Anonymous
TOKEN = "oauth:"
chat_lines = []
current_channel = None
chat_thread = None
stop_event = threading.Event()

def connect_to_chat(channel, stop_event):
    global chat_lines
    chat_lines.clear()  # Clear old messages
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
                parts = response.split(":", 2)
                if len(parts) >= 3:
                    message = parts[2].strip()
                    if moderate_message(message):
                        chat_lines.append(message)
        except:
            break  # Socket closed or interrupted

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


@app.route('/chat')
def stream_chat():
    def stream():
        prev_len = 0
        while True:
            if len(chat_lines) > prev_len:
                for line in chat_lines[prev_len:]:
                    yield f"data: {line}\n\n"
                prev_len = len(chat_lines)
    return Response(stream(), mimetype='text/event-stream')

if __name__ == "__main__":
    app.run(debug=True)
