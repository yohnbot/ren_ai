from flask import Flask, request, jsonify, send_from_directory
import json
import os
import time
import requests
import pyttsx3
import logging
from threading import Lock
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
    TWITCH_CHANNEL = config.get("TWITCH_CHANNEL", "")

# Persona Class
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
                        self.traits[current_section][key.strip().lower()] = value.strip()
            logger.info("Persona loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load persona: {str(e)}")

    def apply_style(self, text, emotion="neutral"):
        """Apply anime-style modifications"""
        if emotion in self.traits['Phrases']:
            return self.traits['Phrases'][emotion].replace('{text}', text)
        return f"{text} desu~!"  # Default Japanese suffix

# Initialize persona
persona = Persona()

# Response handling
def load_responses():
    try:
        with open(RESPONSES_PATH, 'r') as f:
            responses = json.load(f)
        # Convert keys to lowercase for case-insensitive matching
        return {k.lower(): v for k, v in responses.items()}
    except Exception as e:
        logger.error(f"Failed to load responses: {str(e)}")
        return {}

def get_api_response(prompt):
    """Fallback to DeepSeek/DuckDuckGo"""
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
            return response.json().get('choices', [{}])[0].get('message', {}).get('content', "")
    except Exception as e:
        logger.error(f"API error: {str(e)}")
    
    # Fallback to DuckDuckGo
    try:
        params = {"q": prompt, "format": "json", "no_html": 1}
        ddg = requests.get("https://api.duckduckgo.com/", params=params, timeout=5)
        if ddg.ok:
            return ddg.json().get("Abstract", "Sorry, I couldn't find an answer.")
    except:
        pass
    
    return "Mou... I don't know the answer desu~ (´･ω･`)"

def handle_query(prompt):
    normalized_prompt = prompt.strip().lower()
    responses = load_responses()
    
    # 1. Check exact matches
    if normalized_prompt in responses:
        return persona.apply_style(responses[normalized_prompt])
    
    # 2. Check partial matches (e.g., "hello there" -> "hello")
    for key, response in responses.items():
        if key in normalized_prompt:
            return persona.apply_style(response)
    
    # 3. Special behaviors
    if any(greeting in normalized_prompt for greeting in ["hello", "hi", "konnichiwa"]):
        return persona.traits['Behavior'].get('greeting', 'Konnichiwa!')
    
    if any(bye in normalized_prompt for bye in ["bye", "goodbye", "sayonara"]):
        return persona.traits['Behavior'].get('farewell', 'Ja ne~!')
    
    # 4. Fallback to APIs
    api_response = get_api_response(prompt)
    return persona.apply_style(api_response)

# TTS Engine
def generate_tts(text):
    output_file = os.path.join('static', 'response.mp3')
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 160)  # Slightly faster for anime-style
        engine.setProperty('volume', 0.9)
        engine.save_to_file(text, output_file)
        engine.runAndWait()
        return output_file
    except Exception as e:
        logger.error(f"TTS failed: {str(e)}")
        return None

# Routes
@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/generate', methods=['POST'])
def generate():
    prompt = request.json.get('prompt', '').strip()
    if not prompt:
        return jsonify({"error": "Empty query"}), 400
    
    response = handle_query(prompt)
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
    return jsonify({"status": "Persona reloaded", "traits": dict(persona.traits)})

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)