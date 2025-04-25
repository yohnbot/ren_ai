let controller = null;
let isProcessing = false;
let currentAudio = null;
let typingIntervals = [];

document.addEventListener("DOMContentLoaded", () => {
  initializeChat();
  setupTwitchFeed();
});

function initializeChat() {
  document.getElementById("sendBtn").addEventListener("click", sendMessage);
  document.getElementById("stopBtn").addEventListener("click", stopProcess);
  document.getElementById("userInput").addEventListener("keypress", (e) => {
    if (e.key === "Enter" && !isProcessing) {
      e.preventDefault();
      sendMessage();
    }
  });
}

function addTwitchMessage(user, message) {
  const twitchChat = document.getElementById("twitchChat");
  const messageDiv = document.createElement("div");
  messageDiv.className = "twitch-message";
  messageDiv.innerHTML = `<span class="twitch-user">${user}:</span> ${message}`;
  twitchChat.appendChild(messageDiv);
  app.twitchChat.scrollTop = twitchChat.scrollHeight;

  // Auto-remove with fade-out
  setTimeout(() => {
    messageDiv.classList.add("fade-out");
    setTimeout(() => messageDiv.remove(), 1000);
  }, 10000);
}

async function sendMessage() {
  if (isProcessing) return;

  const input = document.getElementById("userInput");
  const prompt = input.value.trim();
  if (!prompt) return;

  isProcessing = true;
  toggleInputs(true);
  addMessage(prompt, "user");
  input.value = "";

  try {
    controller = new AbortController();
    await fetch("/stop", { method: "POST" });

    const response = await fetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
      signal: controller.signal,
    });

    if (!response.ok) throw new Error("Request failed");
    const data = await response.json();

    addMessage(data.text, "bot");
    await playTTS(data.text);
  } catch (err) {
    if (err.name !== "AbortError") {
      addMessage(`Error: ${err.message}`, "system");
    }
  } finally {
    isProcessing = false;
    toggleInputs(false);
    controller = null;
  }
}

async function stopProcess() {
  if (controller) controller.abort();
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
    addMessage("TTS stopped", "system");
  }

  typingIntervals.forEach(clearInterval);
  typingIntervals = [];

  isProcessing = false;
  toggleInputs(false);
  await fetch("/stop", { method: "POST" });
}

async function playTTS(text) {
  try {
    const cleanedText = text
      .replace(/\*/g, "")
      .replace(/[\u{1F600}-\u{1F6FF}\u{2600}-\u{27BF}\u{2B50}\u{2B55}]/gu, "");

    const response = await fetch("/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: cleanedText }),
    });

    if (!response.ok) throw new Error("TTS failed");

    const audioUrl = (await response.json()).audio_url;
    currentAudio = new Audio(audioUrl);
    document.getElementById("stopBtn").style.display = "block";

    await new Promise((resolve, reject) => {
      currentAudio.play();
      currentAudio.addEventListener("ended", resolve);
      currentAudio.addEventListener("error", reject);
    });
  } catch (err) {
    console.error("TTS Error:", err);
  } finally {
    document.getElementById("stopBtn").style.display = "none";
    currentAudio = null;
  }
}

function addMessage(text, sender) {
  const chatArea = document.getElementById("chatArea");
  const messageDiv = document.createElement("div");

  const classes = {
    user: "user-message",
    bot: "bot-message",
    system: "system-message",
  };

  const labels = {
    user: "You:",
    bot: "RenAI:",
    system: "System:",
  };

  messageDiv.className = `message ${classes[sender]}`;
  messageDiv.innerHTML = `
    <div class="message-label">${labels[sender]}</div>
    <div class="message-content"></div>
  `;
  chatArea.appendChild(messageDiv);
  chatArea.scrollTop = chatArea.scrollHeight;

  const contentDiv = messageDiv.querySelector(".message-content");
  if (sender === "bot") {
    const typingInterval = typeMessage(contentDiv, text, 50);
    typingIntervals.push(typingInterval);
  } else {
    contentDiv.textContent = text;
  }
}

function typeMessage(element, message, delay = 0) {
  let i = 0;
  element.textContent = "";
  const interval = setInterval(() => {
    element.textContent += message.charAt(i);
    i++;
    if (i === message.length) clearInterval(interval);
  }, delay);
  return interval;
}

function toggleInputs(disabled) {
  document.getElementById("sendBtn").disabled = disabled;
  document.getElementById("userInput").disabled = disabled;
  document.getElementById("stopBtn").style.display = disabled
    ? "block"
    : "none";
}
