let controller = null;
let isProcessing = false;
let currentAudio = null;
let typingIntervals = [];
let lastUserInputTime = Date.now();
const AUTO_CONVERSATION_INTERVAL = 25000;

document.addEventListener("DOMContentLoaded", () => {
  initializeChat();
  setupTwitchFeed();
  startAutoConversation();
});

function initializeChat() {
  const userInput = document.getElementById("userInput");
  document.getElementById("sendBtn").addEventListener("click", sendMessage);
  document.getElementById("stopBtn").addEventListener("click", stopProcess);

  userInput.addEventListener("input", pauseAutoConversation);
  userInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter" && !isProcessing) {
      e.preventDefault();
      sendMessage();
    }
  });
}

function setupTwitchFeed() {
  const eventSource = new EventSource("/twitch_chat_stream");

  eventSource.onmessage = async ({ data }) => {
    const { user, message } = JSON.parse(data);
    addMessage(`${user}: ${message}`, "user");
    await handleIncomingMessage(message);
  };
}

async function handleIncomingMessage(message) {
  if (isProcessing) return;

  isProcessing = true;
  toggleInputs(true);

  try {
    const response = await fetchWithAbort("/generate", { prompt: message });
    addMessage(response.text, "bot");
    await playTTS(response.text);
  } catch (err) {
    if (err.name !== "AbortError") {
      addMessage(`Error: ${err.message}`, "system");
    }
  } finally {
    isProcessing = false;
    toggleInputs(false);
  }
}

async function sendMessage() {
  if (isProcessing) return;

  const input = document.getElementById("userInput");
  const prompt = input.value.trim();
  if (!prompt) return;

  resetAutoConversationTimer();
  isProcessing = true;
  toggleInputs(true);

  addMessage(prompt, "user");
  input.value = "";

  try {
    const response = await fetchWithAbort("/generate", { prompt });
    addMessage(response.text, "bot");
    await playTTS(response.text);
  } catch (err) {
    if (err.name !== "AbortError") {
      addMessage(`Error: ${err.message}`, "system");
    }
  } finally {
    isProcessing = false;
    toggleInputs(false);
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
    const cleanedText = sanitizeTextForTTS(text);
    const { audio_url } = await postJSON("/tts", { text: cleanedText });

    currentAudio = new Audio(audio_url);
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

  messageDiv.className = `message ${sender}-message`;
  messageDiv.innerHTML = `
    <div class="message-label">${
      {
        user: "You:",
        bot: "RenAI:",
        system: "System:",
      }[sender]
    }</div>
    <div class="message-content"></div>
  `;
  chatArea.appendChild(messageDiv);
  chatArea.scrollTop = chatArea.scrollHeight;

  const contentDiv = messageDiv.querySelector(".message-content");
  if (sender === "bot") {
    typingIntervals.push(typeMessage(contentDiv, text, 50));
  } else {
    contentDiv.textContent = text;
  }
}

function typeMessage(element, message, delay = 0) {
  let i = 0;
  element.textContent = "";
  const interval = setInterval(() => {
    element.textContent += message.charAt(i++);
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

function resetAutoConversationTimer() {
  lastUserInputTime = Date.now();
  fetch("/reset_auto_conversation_timer", { method: "POST" });
}

function pauseAutoConversation() {
  fetch("/pause_auto_conversation", { method: "POST" });
}

function startAutoConversation() {
  setInterval(async () => {
    if (Date.now() - lastUserInputTime > AUTO_CONVERSATION_INTERVAL) {
      await generateAutoMessage();
    }
  }, AUTO_CONVERSATION_INTERVAL);
}

async function generateAutoMessage() {
  try {
    const response = await postJSON("/generate_auto_message");
    addMessage(response.text, "bot");
    await playTTS(response.text);
  } catch (err) {
    console.error("Auto-message error:", err);
  }
}

function sanitizeTextForTTS(text) {
  return text
    .replace(/\*/g, "")
    .replace(/[\u{1F600}-\u{1F6FF}\u{2600}-\u{27BF}\u{2B50}\u{2B55}]/gu, "");
}

// Unified fetch helpers
async function fetchWithAbort(url, body = {}) {
  controller = new AbortController();
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: controller.signal,
  });
  if (!response.ok) throw new Error("Request failed");
  return await response.json();
}

async function postJSON(url, body = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`Request failed: ${response.statusText}`);
  return await response.json();
}
