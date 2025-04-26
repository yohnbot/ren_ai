from flask import Flask, request, jsonify, send_from_directory
import json
import os
import re  # Added for character filtering
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
                        # Filter unwanted characters during load
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
        
        # Filter unwanted characters before returning
        return re.sub(r'[#`~()-]', '', base_text)

# Initialize persona
persona = Persona()

def sanitize_text(text):
    """Remove unwanted characters from any text"""
    return re.sub(r'[#`~-]', '', text)

def load_responses():
    try:
        with open(RESPONSES_PATH, 'r') as f:
            responses = json.load(f)
        # Convert keys to lowercase and sanitize values
        return {k.lower(): sanitize_text(v) for k, v in responses.items()}
    except Exception as e:
        logger.error(f"Failed to load responses: {str(e)}")
        return {}

def get_api_response(prompt):
    """Fallback to DeepSeek/DuckDuckGo with sanitization"""
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
    normalized_prompt = sanitize_text(prompt.strip().lower())
    responses = load_responses()
    
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
        # Sanitize text before TTS generation
        clean_text = sanitize_text(text)
        engine.save_to_file(clean_text, output_file)
        engine.runAndWait()
        return output_file
    except Exception as e:
        logger.error(f"TTS failed: {str(e)}")
        return None

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
    return jsonify({"status": "Persona reloaded"})

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
