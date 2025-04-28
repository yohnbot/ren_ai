from flask import Flask, request, jsonify, send_from_directory
import json
import os
import re
import time
import requests
import pyttsx3
import random
import logging
import socket
from threading import Thread, Event

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')

# File paths
CONFIG_PATH = 'config.json'
RESPONSES_PATH = 'data/responses.json'
PERSONA_PATH = 'data/persona.json'
CONVERSATION_PATH = 'data/conversation.json'

# Load config
with open(CONFIG_PATH) as f:
    config = json.load(f)
    DEEPSEEK_API_KEY = config.get("DEEPSEEK_API_KEY", "")
    TWITCH_OAUTH_TOKEN = config.get("TWITCH_OAUTH_TOKEN", "")
    TWITCH_CHANNEL = config.get("TWITCH_CHANNEL", "").lower()

# Global flags
last_user_input_time = time.time()
auto_conversation_paused = True  # Start paused
greeted = False
web_app_loaded = Event()

# Classes
class Persona:
    def __init__(self):
        self.traits = {'Identity': {}, 'Behavior': {}, 'Phrases': {}}
        self.load()

    def load(self):
        try:
            with open(PERSONA_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for section in self.traits:
                    if section in data:
                        self.traits[section] = data[section]
            logger.info("Persona loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load persona: {str(e)}")

    def apply_style(self, text, emotion="neutral"):
        phrase_template = self.traits['Phrases'].get(emotion, '{text}')
        styled_text = phrase_template.replace('{text}', text)
        return re.sub(r'[#`~()-]', '', styled_text)

# Instantiate persona
persona = Persona()

# Utilities
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

def save_responses(responses):
    try:
        with open(RESPONSES_PATH, 'w') as f:
            json.dump(responses, f, indent=4)
        logger.info("Responses saved successfully.")
    except Exception as e:
        logger.error(f"Failed to save responses: {str(e)}")

def get_api_response(prompt):
    try:
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
        payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}]}
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=10
        )
        if response.ok:
            return sanitize_text(response.json()['choices'][0]['message']['content'])
    except Exception as e:
        logger.error(f"DeepSeek API error: {str(e)}")

    # Fallback DuckDuckGo
    try:
        params = {"q": prompt, "format": "json", "no_html": 1}
        ddg = requests.get("https://api.duckduckgo.com/", params=params, timeout=5)
        if ddg.ok:
            data = ddg.json()
            abstract = data.get("Abstract", "")
            answer = data.get("Answer", "")
            content = abstract or answer or "Sorry, I couldn't find a short answer."
            sentences = re.split(r'[.!?]', content)
            return sanitize_text(". ".join(sentences[:2]) + ".")
    except Exception as e:
        logger.error(f"DuckDuckGo fallback error: {str(e)}")

    return sanitize_text("Mou... I don't know the answer desu (´･ω･`)")

def handle_query(prompt):
    normalized_prompt = sanitize_text(prompt.lower().strip())
    responses = load_responses()

    if any(creator in normalized_prompt for creator in ["creator", "who made you", "who created you"]):
        return persona.apply_style("I was created by John!")

    if normalized_prompt in responses:
        return persona.apply_style(responses[normalized_prompt])

    api_response = get_api_response(prompt)
    styled_response = persona.apply_style(api_response)

    responses[normalized_prompt] = styled_response
    save_responses(responses)

    return styled_response

def generate_tts(text):
    output_path = os.path.join('static', 'response.mp3')
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 0.9)
        clean_text = sanitize_text(text)
        engine.save_to_file(clean_text, output_path)
        engine.runAndWait()
        return output_path
    except Exception as e:
        logger.error(f"TTS generation error: {str(e)}")
        return None

def send_twitch_message(message):
    try:
        irc = socket.socket()
        irc.connect(('irc.chat.twitch.tv', 6667))
        irc.send(f"PASS {TWITCH_OAUTH_TOKEN}\n".encode('utf-8'))
        irc.send(f"NICK {TWITCH_CHANNEL}\n".encode('utf-8'))
        irc.send(f"JOIN #{TWITCH_CHANNEL}\n".encode('utf-8'))
        irc.send(f"PRIVMSG #{TWITCH_CHANNEL} :{message}\n".encode('utf-8'))
        logger.info(f"Sent Twitch message: {message}")
        irc.close()
    except Exception as e:
        logger.error(f"Twitch message error: {str(e)}")

def load_conversation_triggers():
    try:
        with open(CONVERSATION_PATH, 'r') as f:
            return json.load(f).get('triggers', [])
    except Exception as e:
        logger.error(f"Failed loading conversation triggers: {str(e)}")
        return []

# Flask Routes
@app.route('/')
def index():
    web_app_loaded.set()  # Web app is loaded, allow auto-conversation
    return send_from_directory('templates', 'index.html')

@app.route('/generate', methods=['POST'])
def generate():
    global last_user_input_time, auto_conversation_paused
    prompt = request.json.get('prompt', '').strip()
    if not prompt:
        return jsonify({"error": "Empty query"}), 400

    last_user_input_time = time.time()
    auto_conversation_paused = True  # Pause during user input

    response = handle_query(prompt)
    return jsonify({"text": response})

@app.route('/tts', methods=['POST'])
def tts():
    global auto_conversation_paused
    text = request.json.get('text', '')
    if not text:
        return jsonify({"error": "No text provided"}), 400

    auto_conversation_paused = True  # Pause auto-convo during TTS

    output_file = generate_tts(text)
    if not output_file:
        return jsonify({"error": "TTS generation failed"}), 500

    auto_conversation_paused = False  # Resume after TTS
    return jsonify({"audio_url": f"/static/response.mp3?t={time.time()}"})

@app.route('/reset_auto_conversation_timer', methods=['POST'])
def reset_auto_conversation_timer():
    global last_user_input_time, auto_conversation_paused
    last_user_input_time = time.time()
    auto_conversation_paused = False
    return jsonify({"status": "Timer reset"})

@app.route('/pause_auto_conversation', methods=['POST'])
def pause_auto_conversation():
    global auto_conversation_paused
    auto_conversation_paused = True
    return jsonify({"status": "Auto-conversation paused"})

@app.route('/generate_auto_message', methods=['POST'])
def generate_auto_message():
    try:
        triggers = load_conversation_triggers()
        other_triggers = [t for t in triggers if t.get("type") != "greeting"]
        if other_triggers:
            trigger = random.choice(other_triggers)
            response = persona.apply_style(trigger["text"])
            return jsonify({"text": response})
        return jsonify({"text": "I'm feeling a bit quiet right now..."}), 200
    except Exception as e:
        logger.error(f"Auto-message generation error: {str(e)}")
        return jsonify({"text": "Oops, something went wrong."}), 500

# Auto Conversation Thread
def auto_conversation():
    global last_user_input_time, auto_conversation_paused, greeted

    triggers = load_conversation_triggers()
    while True:
        if web_app_loaded.is_set() and not auto_conversation_paused:
            current_time = time.time()

            if not greeted:
                greeting_triggers = [t for t in triggers if t.get("type") == "greeting"]
                if greeting_triggers:
                    trigger = random.choice(greeting_triggers)
                    send_twitch_message(persona.apply_style(trigger['text']))
                    greeted = True
                    last_user_input_time = current_time

            elif current_time - last_user_input_time > 25:
                other_triggers = [t for t in triggers if t.get("type") != "greeting"]
                if other_triggers:
                    trigger = random.choice(other_triggers)
                    send_twitch_message(persona.apply_style(trigger['text']))
                    last_user_input_time = current_time

        time.sleep(1)

Thread(target=auto_conversation, daemon=True).start()

# Main
if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
