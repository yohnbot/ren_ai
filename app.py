from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from flask_cors import CORS
import os
import json
import time
import requests
import pyttsx3
import logging
import threading
import asyncio
from queue import Queue
from threading import Lock
from twitchio.ext import commands

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')

# Load configurations
CONFIG_PATH = 'config.json'
RESPONSES_PATH = 'data/responses.json'

with open(CONFIG_PATH) as f:
    config = json.load(f)
    DEEPSEEK_API_KEY = config["DEEPSEEK_API_KEY"]
    TWITCH_OAUTH_TOKEN = config["TWITCH_OAUTH_TOKEN"]
    TWITCH_CHANNEL = config["TWITCH_CHANNEL"]

# Thread-safe message processing
message_queue = Queue()
response_queue = Queue()
processing_lock = Lock()

# Global variables
stop_event = threading.Event()

# Twitch Bot
class TwitchBot(commands.Bot):
    def __init__(self):
        super().__init__(
            token=TWITCH_OAUTH_TOKEN,
            prefix="!",
            initial_channels=[TWITCH_CHANNEL]
        )

    async def event_ready(self):
        logger.info(f"Twitch bot logged in as {self.nick}")

    async def event_message(self, message):
        if message.echo or not message.content:
            return
        
        # Add message to the thread-safe queue
        with processing_lock:
            message_queue.put({
                "user": message.author.name,
                "text": message.content,
                "timestamp": time.time()
            })

# Run Twitch bot in background
def run_twitch_bot():
    # Create a new event loop for the thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Initialize and run the bot
    bot = TwitchBot()
    bot.run()

threading.Thread(target=run_twitch_bot, daemon=True).start()

# Worker for processing AI responses
def ai_response_worker():
    while not stop_event.is_set():
        with processing_lock:
            if not message_queue.empty():
                msg = message_queue.get()
                response = handle_query(msg['text'])
                response_queue.put({
                    'user': 'RenAI',
                    'text': response,
                    'timestamp': time.time(),
                    'original_user': msg['user']
                })
        time.sleep(0.1)  # Prevent CPU overuse

# Start AI response worker
threading.Thread(target=ai_response_worker, daemon=True).start()

# Helper Functions
def is_trending_query(prompt):
    trending_keywords = ['new', 'latest', 'trending', 'update', 'current', 'recent']
    return any(keyword in prompt.lower() for keyword in trending_keywords)

def load_responses():
    try:
        with open(RESPONSES_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Responses load error: {str(e)}")
        return {}

def save_response(prompt, response):
    try:
        responses = load_responses()
        responses[prompt] = response
        with open(RESPONSES_PATH, 'w') as f:
            json.dump(responses, f, indent=2)
    except Exception as e:
        logger.error(f"Save response failed: {str(e)}")

def deepseek_query(prompt):
    try:
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
        payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}]}
        response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        return response.json().get('choices', [{}])[0].get('message', {}).get('content')
    except requests.RequestException as e:
        logger.error(f"DeepSeek API error: {str(e)}")
        return None

def get_web_search_results(query):
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("Abstract") or (data.get("RelatedTopics", [{}])[0].get("Text")) or "No results found."
    except requests.RequestException as e:
        logger.error(f"DuckDuckGo API error: {str(e)}")
        return "No results found."

def handle_query(prompt):
    responses = load_responses()
    
    # Normalize the prompt and response keys to lowercase for case-insensitive matching
    normalized_prompt = prompt.lower()
    
    # Check for exact lowercase match first (efficient)
    if normalized_prompt in responses:
        return responses[normalized_prompt]
    
    # Fallback: Check for case-insensitive match in keys (slower but thorough)
    for key in responses:
        if key.lower() == normalized_prompt:
            return responses[key]
    
    # Proceed with API/web search if no cached response
    deepseek_response = deepseek_query(prompt)
    if deepseek_response:
        save_response(prompt, deepseek_response)
        return deepseek_response
    
    web_search_result = get_web_search_results(prompt)
    if web_search_result != "No results found.":
        save_response(prompt, web_search_result)
        return web_search_result
    
    return "Sorry, I couldn't find an answer to your query."

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    try:
        data = request.json
        prompt = data['prompt'].strip().lower()
        if not prompt:
            return jsonify({'error': 'Empty query'}), 400

        response = handle_query(prompt)
        return jsonify({'text': response})

    except Exception as e:
        logger.error(f"Generate error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/tts', methods=['POST'])
def tts():
    try:
        text = request.json['text']
        output_file = 'static/response.mp3'
        
        if os.path.exists(output_file):
            os.remove(output_file)
            
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.save_to_file(text, output_file)
        engine.runAndWait()
        
        return jsonify({'audio_url': f'/static/response.mp3?t={time.time()}'})
    except Exception as e:
        logger.error(f"TTS error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/stop', methods=['POST'])
def stop():
    stop_event.set()
    return jsonify({'status': 'stopped'})

@app.route('/get_messages')
def get_messages():
    after = float(request.args.get('after', 0))
    messages = []
    
    with processing_lock:
        while not response_queue.empty():
            msg = response_queue.get()
            if msg['timestamp'] > after:
                messages.append(msg)
    
    return jsonify(messages)

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)