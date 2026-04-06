const API = "";

// DOM
const inputText = document.getElementById("input-text");
const outputText = document.getElementById("output-text");
const btnTranslate = document.getElementById("btn-translate");
const btnClear = document.getElementById("btn-clear");
const btnCopy = document.getElementById("btn-copy");
const btnSpeak = document.getElementById("btn-speak");
const btnMic = document.getElementById("btn-mic");
const btnClearHistory = document.getElementById("btn-clear-history");
const charCount = document.getElementById("char-count");
const translationTime = document.getElementById("translation-time");
const historyList = document.getElementById("history-list");
const recordingIndicator = document.getElementById("recording-indicator");

const btnLangToggle = document.getElementById("btn-lang-toggle");

// State
let isTranslating = false;
let history = JSON.parse(localStorage.getItem("trad_history") || "[]");
let recognition = null;
let isRecording = false;
let voiceLang = "fr"; // "fr" or "es" — language for speech recognition

// Init lang toggle button
btnLangToggle.classList.add("fr");
btnLangToggle.textContent = "FR";

btnLangToggle.addEventListener("click", () => {
    if (voiceLang === "fr") {
        voiceLang = "es";
        btnLangToggle.textContent = "ES";
        btnLangToggle.classList.remove("fr");
        btnLangToggle.classList.add("es");
    } else {
        voiceLang = "fr";
        btnLangToggle.textContent = "FR";
        btnLangToggle.classList.remove("es");
        btnLangToggle.classList.add("fr");
    }
    // Reset recognition so it picks up new lang
    if (recognition) { try { recognition.stop(); } catch {} recognition = null; }
});

// === Character count ===
inputText.addEventListener("input", () => {
    charCount.textContent = inputText.value.length;
});

// === Translate (streaming) ===
async function translateText() {
    const text = inputText.value.trim();
    if (!text || isTranslating) return;

    isTranslating = true;
    btnTranslate.disabled = true;
    btnTranslate.classList.add("loading");
    outputText.innerHTML = "";
    outputText.classList.remove("placeholder");
    translationTime.textContent = "";
    btnCopy.style.display = "none";
    btnSpeak.style.display = "none";

    const t0 = performance.now();
    let fullText = "";

    try {
        const res = await fetch(`${API}/api/translate/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                try {
                    const d = JSON.parse(line.slice(6));
                    if (d.type === "text") {
                        fullText += d.content;
                        outputText.textContent = fullText;
                    } else if (d.type === "done") {
                        fullText = d.full_text;
                        outputText.textContent = fullText;
                    }
                } catch {}
            }
        }
    } catch (err) {
        outputText.textContent = `Erreur: ${err.message}`;
    }

    const elapsed = ((performance.now() - t0) / 1000).toFixed(1);
    translationTime.textContent = `${elapsed}s`;

    if (fullText) {
        btnCopy.style.display = "flex";
        btnSpeak.style.display = "flex";
        addToHistory(text, fullText);
    }

    isTranslating = false;
    btnTranslate.disabled = false;
    btnTranslate.classList.remove("loading");
}

// === Keyboard shortcut: Ctrl+Enter or Enter to translate ===
inputText.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        translateText();
    }
    // Enter sans Shift traduit aussi (pour phrases simples)
    if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey) {
        e.preventDefault();
        translateText();
    }
});

btnTranslate.addEventListener("click", translateText);

// === Clear ===
btnClear.addEventListener("click", () => {
    inputText.value = "";
    outputText.innerHTML = '<span class="placeholder">La traduction apparaitra ici...</span>';
    charCount.textContent = "0";
    translationTime.textContent = "";
    btnCopy.style.display = "none";
    btnSpeak.style.display = "none";
    inputText.focus();
});

// === Copy (with fallback for HTTP) ===
btnCopy.addEventListener("click", async () => {
    const text = outputText.textContent;
    if (!text) return;
    try {
        await navigator.clipboard.writeText(text);
    } catch {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
    }
    btnCopy.style.background = "var(--accent)";
    btnCopy.style.color = "#111";
    setTimeout(() => {
        btnCopy.style.background = "";
        btnCopy.style.color = "";
    }, 800);
});

// === TTS (browser) ===
btnSpeak.addEventListener("click", () => {
    const text = outputText.textContent;
    if (!text) return;

    speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(text);

    // Detect language of output (opposite of input)
    if (isSpanish(inputText.value)) {
        utt.lang = "fr-FR";
    } else {
        utt.lang = "es-ES";
    }
    utt.rate = 1.0;
    speechSynthesis.speak(utt);
});

// === Simple language detection ===
function isSpanish(text) {
    const esMarkers = /[¿¡ñáéíóúü]|(\b(el|la|los|las|un|una|unos|unas|es|está|son|hola|como|qué|por|para|pero|con|sin|más|muy|también|tiene|hace|puede|esta|ese|esa|esto|aquí|ahora|donde|cuando|porque|si|no|ya|hay|ser|estar|tener|hacer|poder|decir|saber|querer|llegar|pasar|deber|poner|parecer|quedar|creer|hablar|llevar|dejar|seguir|encontrar|llamar|venir|pensar|salir|volver|tomar|conocer|vivir|sentir|tratar|mirar|contar|empezar|esperar|buscar|existir|entrar|trabajar|escribir|perder|producir|ocurrir|entender|pedir|recibir|recordar|terminar|permitir|aparecer|conseguir|comenzar|servir|sacar|necesitar|mantener|resultar|leer|caer|cambiar|presentar|crear|abrir|considerar|oír|acabar|convertir|ganar|formar)\b)/i;
    return esMarkers.test(text);
}

// === Voice input ===
function initRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return null;
    const r = new SR();
    r.continuous = true;
    r.interimResults = true;
    r.lang = voiceLang === "es" ? "es-ES" : "fr-FR";

    let finalText = "";
    let silenceTimer = null;

    r.onresult = (e) => {
        let interim = "";
        finalText = "";
        for (let i = 0; i < e.results.length; i++) {
            if (e.results[i].isFinal) {
                finalText += e.results[i][0].transcript;
            } else {
                interim += e.results[i][0].transcript;
            }
        }

        const display = finalText + interim;
        inputText.value = display;
        charCount.textContent = display.length;
        recordingIndicator.querySelector("span").textContent = display || (voiceLang === "es" ? "Escuchando..." : "Ecoute...");

        // Auto-translate after 1.5s of silence following final result
        clearTimeout(silenceTimer);
        if (finalText.trim()) {
            silenceTimer = setTimeout(() => {
                stopRecording();
                translateText();
            }, 1500);
        }
    };

    r.onerror = () => stopRecording();
    r.onend = () => {
        // If we have text and recording stopped naturally, translate
        if (isRecording && finalText.trim()) {
            stopRecording();
            translateText();
        } else if (isRecording) {
            // Restart if no result yet (browser timeout)
            try { r.start(); } catch {}
        }
    };

    return r;
}

function startRecording() {
    // Recreate recognition each time to pick up current voiceLang
    recognition = initRecognition();
    if (!recognition) return alert("Navigateur non supporté. Utilise Chrome.");

    isRecording = true;
    btnMic.classList.add("active");
    recordingIndicator.style.display = "flex";
    recordingIndicator.querySelector("span").textContent = voiceLang === "es" ? "Escuchando..." : "Ecoute...";
    recognition.start();
}

function stopRecording() {
    isRecording = false;
    btnMic.classList.remove("active");
    recordingIndicator.style.display = "none";
    if (recognition) try { recognition.stop(); } catch {}
}

btnMic.addEventListener("click", () => {
    isRecording ? stopRecording() : startRecording();
});

// === History ===
function addToHistory(original, translated) {
    // Avoid duplicates
    history = history.filter(h => h.original !== original);
    history.unshift({ original, translated, time: Date.now() });
    if (history.length > 20) history = history.slice(0, 20);
    localStorage.setItem("trad_history", JSON.stringify(history));
    renderHistory();
}

function renderHistory() {
    historyList.innerHTML = "";
    for (const h of history.slice(0, 10)) {
        const li = document.createElement("li");
        const origShort = h.original.length > 40 ? h.original.slice(0, 40) + "..." : h.original;
        const tradShort = h.translated.length > 40 ? h.translated.slice(0, 40) + "..." : h.translated;
        li.innerHTML = `<span class="original">${escHtml(origShort)}</span><span class="sep">→</span><span class="translated">${escHtml(tradShort)}</span>`;
        li.addEventListener("click", () => {
            inputText.value = h.original;
            outputText.textContent = h.translated;
            charCount.textContent = h.original.length;
            btnCopy.style.display = "flex";
            btnSpeak.style.display = "flex";
        });
        historyList.appendChild(li);
    }
}

function escHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

btnClearHistory.addEventListener("click", () => {
    history = [];
    localStorage.removeItem("trad_history");
    renderHistory();
});

// Init
renderHistory();
