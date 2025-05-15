# Ren AI Vtuber
An AI powered Virtual Youtuber that uses Deepseek and Duckduckgo to answer questions. It stores questions in a dictionary called response.json to help answer already asked question. 
will be using a virutal audio cable and vtube studio to make a model work with the tts of the web application for the demo.

## Snapshot of web application
![image](https://github.com/user-attachments/assets/a35a0d96-c695-4c9f-b181-30cdfcbc1c64)
![Screenshot 2025-04-24 204534](https://github.com/user-attachments/assets/35efa11d-1593-4ddf-9202-12f04b785282)


---

## Features

- Conversational AI using DeepSeek and DuckDuckGo
- Real-time Text-to-Speech (TTS)
- Audio routed to VTube Studio via Virtual Audio Cable for lip-sync
- Flask-based web interface
- Persistent response memory (via JSON)

---
## 🧰 Requirements

- Python 3.10+
- pip (Python package manager)
- Git
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/)
- [VTube Studio](https://denchisoft.com/)
- Microsoft Text-to-Speech voices (e.g. Microsoft Aria)
---
## TTS voice
To customise the voice of pyttsx3 it can only use the Microsoft text to speech this can be found on settings.
You may require to restart your computer once download is finished

![image](https://github.com/user-attachments/assets/135483e8-f1f6-4f09-af24-19ec2ed0ffc8)
![image](https://github.com/user-attachments/assets/38b9fda4-5b6a-470c-85d8-6b986a89e0af)

Ensure that it is changed in "Text to Speech" in the Control panel

---

## 🔧 Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/yohnbot/ren_ai.git
cd ren_ai
```
Install Python Dependencies
```bash
pip install -r requirements.txt
```
---
### 2. Set Up Virtual Audio Cable
1. Install VB-Audio Cable
Download and install from: https://lualucky.itch.io/vts-desktop-audio-plugin
Using this plugin for Vtube Studio to listen to the desktop audio to sync animation with the mouth of the avatar

3. Route TTS Audio Through Virtual Cable
Open Windows Sound Settings.

Set Output device to CABLE Input (VB-Audio Virtual Cable).

--- 
### 3. VTube Studio Configuration
1. Install & Launch VTube Studio
Download from https://denchisoft.com/ or Steam, install, and load your avatar model.

2. Follow this youtube tutorial to route audio from VTube Studio to The plugin https://youtu.be/IiZ0JrGd6BQ

3. Add custom animation to avatar such as blink etc. and ensure that the you use the plug in for the mouth movement.



Future improvements that can be done for this project as it is out of scope:
- Update TTS
- Fully intergrate with Twitch and Youtube
- Include animations depending on the feelings such as happy, sad and crying as there are lots of emotions to convey.
- Speech to Text using mozilla deep speech
