from flask import Flask, request, jsonify, send_from_directory, Response
import json
import os
import re
import time
import requests
import pyttsx3
import logging
import socket
from threading import Lock, Thread
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')

# File paths
CONFIG_PATH = 'config.json'
RESPONSES_PATH = 'data/responses.json'
PERSONA_PATH = 'data/persona.txt'

# Load config
with open(CONFIG_PATH) as f:
    config = json.load(f)
    DEEPSEEK_API_KEY = config.get("DEEPSEEK_API_KEY", "")
    TWITCH_OAUTH_TOKEN = config.get("TWITCH_OAUTH_TOKEN", "")
    TWITCH_CHANNEL = config.get("TWITCH_CHANNEL", "").lower()

class Persona:
    def __init__(self):
        self.traits = {
            'Identity': defaultdict(str),
            'Behavior': defaultdict(str),
            'Phrases': defaultdict(str)
        }
        self.load()

    def load(self):
        try:
            current_section = None
            with open(PERSONA_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('[') and line.endswith(']'):
                        current_section = line[1:-1]
                    elif '=' in line and current_section:
                        key, value = line.split('=', 1)
                        filtered_value = re.sub(r'[#`~]', '', value.strip())
                        self.traits[current_section][key.strip().lower()] = filtered_value
            logger.info("Persona loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load persona: {str(e)}")

    def apply_style(self, text, emotion="neutral"):
        if emotion in self.traits['Phrases']:
            base_text = self.traits['Phrases'][emotion].replace('{text}', text)
        else:
            base_text = f"{text}"
        return re.sub(r'[#`~()-]', '', base_text)

# Initialize persona
persona = Persona()

def sanitize_text(text):
    return re.sub(r'[#`~-]', '', text)

def load_responses():
    try:
        with open(RESPONSES_PATH, 'r') as f:
            responses = json.load(f)
        return {k.lower(): sanitize_text(v) for k, v in responses.items()}
    except Exception as e:
        logger.error(f"Failed to load responses: {str(e)}")
        return {}

def get_api_response(prompt):
    try:
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}]
        }
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=10
        )
        if response.ok:
            raw_response = response.json().get('choices', [{}])[0].get('message', {}).get('content', "")
            return sanitize_text(raw_response)
    except Exception as e:
        logger.error(f"API error: {str(e)}")

    try:
        params = {"q": prompt, "format": "json", "no_html": 1}
        ddg = requests.get("https://api.duckduckgo.com/", params=params, timeout=5)
        if ddg.ok:
            raw_response = ddg.json().get("Abstract", "Sorry, I couldn't find an answer.")
            return sanitize_text(raw_response)
    except:
        pass

    return sanitize_text("Mou... I don't know the answer desu (´･ω･`)")

def handle_query(prompt):
    # Force English response and handle specific "creator" query
    normalized_prompt = sanitize_text(prompt.strip().lower())
    responses = load_responses()

    # Custom response for "creator" question
    if any(creator_query in normalized_prompt for creator_query in ["creator", "who made you", "who created you"]):
        return persona.apply_style("I was created by John!")

    if normalized_prompt in responses:
        return persona.apply_style(responses[normalized_prompt])

    for key, response in responses.items():
        if key in normalized_prompt:
            return persona.apply_style(response)

    if any(greeting in normalized_prompt for greeting in ["hello", "hi", "konnichiwa"]):
        return persona.traits['Behavior'].get('greeting', 'Konnichiwa!')

    if any(bye in normalized_prompt for bye in ["bye", "goodbye", "sayonara"]):
        return persona.traits['Behavior'].get('farewell', 'Ja ne!')

    api_response = get_api_response(prompt)
    return persona.apply_style(api_response)

def generate_tts(text):
    output_file = os.path.join('static', 'response.mp3')
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 130)
        engine.setProperty('volume', 0.9)
        clean_text = sanitize_text(text)
        engine.save_to_file(clean_text, output_file)
        engine.runAndWait()
        return output_file
    except Exception as e:
        logger.error(f"TTS failed: {str(e)}")
        return None

# New function to send messages back to Twitch chat
def send_twitch_message(message):
    try:
        irc = socket.socket()
        irc.connect((TWITCH_SERVER, TWITCH_PORT))
        irc.send(f"PASS {TWITCH_OAUTH_TOKEN}\n".encode('utf-8'))
        irc.send(f"NICK {TWITCH_CHANNEL}\n".encode('utf-8'))
        irc.send(f"JOIN #{TWITCH_CHANNEL}\n".encode('utf-8'))
        
        # Send a message to the Twitch chat
        irc.send(f"PRIVMSG #{TWITCH_CHANNEL} :{message}\n".encode('utf-8'))
        logger.info(f"Sent message to Twitch chat: {message}")
    except Exception as e:
        logger.error(f"Failed to send message to Twitch chat: {str(e)}")

# New function to process chat messages
def process_message(message):
    response = handle_query(message)
    send_twitch_message(response)  # Send the response to Twitch chat
    return response

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/generate', methods=['POST'])
def generate():
    prompt = request.json.get('prompt', '').strip()
    if not prompt:
        return jsonify({"error": "Empty query"}), 400

    response = process_message(prompt)
    return jsonify({"text": response})

@app.route('/tts', methods=['POST'])
def tts():
    text = request.json.get('text', '')
    if not text:
        return jsonify({"error": "No text provided"}), 400

    output_file = generate_tts(text)
    if not output_file:
        return jsonify({"error": "TTS generation failed"}), 500

    return jsonify({"audio_url": f"/static/response.mp3?t={time.time()}"})

@app.route('/reload_persona', methods=['POST'])
def reload_persona():
    persona.load()
    return jsonify({"status": "Persona reloaded"})

@app.route('/static/<path:filename>')  # Serve static files (like TTS)
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

# ---------------------------
# Twitch Chat Reading Section
# ---------------------------

TWITCH_SERVER = 'irc.chat.twitch.tv'
TWITCH_PORT = 6667
chat_messages = []

def connect_to_twitch_chat():
    irc = socket.socket()
    irc.connect((TWITCH_SERVER, TWITCH_PORT))
    irc.send(f"PASS {TWITCH_OAUTH_TOKEN}\n".encode('utf-8'))
    irc.send(f"NICK {TWITCH_CHANNEL}\n".encode('utf-8'))
    irc.send(f"JOIN #{TWITCH_CHANNEL}\n".encode('utf-8'))

    while True:
        try:
            data = irc.recv(2048).decode('utf-8')
            if data.startswith('PING'):
                irc.send("PONG\n".encode('utf-8'))
            else:
                parts = data.split('PRIVMSG')
                if len(parts) > 1:
                    username = data.split('!', 1)[0][1:]
                    message = parts[1].split(':', 1)[1]
                    chat_messages.append((username, message.strip()))
                    logger.info(f"Twitch chat: {username}: {message.strip()}")
        except Exception as e:
            logger.error(f"Twitch IRC error: {str(e)}")
            break

Thread(target=connect_to_twitch_chat, daemon=True).start()

@app.route('/twitch_chat_stream')
def twitch_chat_stream():
    def event_stream():
        last_index = 0
        while True:
            if len(chat_messages) > last_index:
                user, message = chat_messages[last_index]
                last_index += 1
                yield f"data: {json.dumps({'user': user, 'message': message})}\n\n"
            time.sleep(1)
    return Response(event_stream(), mimetype="text/event-stream")

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
