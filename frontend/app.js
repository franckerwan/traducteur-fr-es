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
let history = [];
try { history = JSON.parse(localStorage.getItem("trad_history") || "[]"); } catch { history = []; }
let recognition = null;
let isRecording = false;
let voiceLang = "fr";
let abortController = null;

// Lang toggle
btnLangToggle.classList.add("fr");
btnLangToggle.textContent = "FR";

btnLangToggle.addEventListener("click", () => {
    const next = voiceLang === "fr" ? "es" : "fr";
    btnLangToggle.textContent = next.toUpperCase();
    btnLangToggle.classList.replace(voiceLang, next);
    voiceLang = next;
    if (isRecording) stopRecording();
});

// Character count (debounced)
let charCountRaf = 0;
inputText.addEventListener("input", () => {
    cancelAnimationFrame(charCountRaf);
    charCountRaf = requestAnimationFrame(() => {
        charCount.textContent = inputText.value.length;
    });
});

// Translate (streaming with retry)
const MAX_RETRIES = 2;
const RETRY_DELAY = 1000;

async function translateText(retryCount = 0) {
    const text = inputText.value.trim();
    if (!text || isTranslating) return;

    isTranslating = true;
    btnTranslate.disabled = true;
    btnTranslate.classList.add("loading");
    outputText.textContent = "";
    outputText.classList.remove("placeholder");
    translationTime.textContent = "";
    btnCopy.style.display = "none";
    btnSpeak.style.display = "none";

    const t0 = performance.now();
    let fullText = "";

    abortController = new AbortController();
    const timeout = setTimeout(() => abortController.abort(), 30000);

    let pendingUpdate = null;
    let retrying = false;

    try {
        const res = await fetch(`${API}/api/translate/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
            signal: abortController.signal,
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

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
                    } else if (d.type === "done") {
                        fullText = d.full_text;
                    }
                } catch {}
            }

            // Batch DOM updates via rAF
            if (!pendingUpdate) {
                pendingUpdate = requestAnimationFrame(() => {
                    outputText.textContent = fullText;
                    pendingUpdate = null;
                });
            }
        }

        // Process any remaining buffer content not terminated by \n
        if (buffer.startsWith("data: ")) {
            try {
                const d = JSON.parse(buffer.slice(6));
                if (d.type === "text") {
                    fullText += d.content;
                } else if (d.type === "done") {
                    fullText = d.full_text;
                }
            } catch {}
        }

        // Final sync update
        if (pendingUpdate) cancelAnimationFrame(pendingUpdate);
        outputText.textContent = fullText;
    } catch (err) {
        if (pendingUpdate) { cancelAnimationFrame(pendingUpdate); pendingUpdate = null; }
        if (err.name === "AbortError") {
            outputText.textContent = "Traduction interrompue (timeout).";
        } else if (retryCount < MAX_RETRIES) {
            retrying = true;
            clearTimeout(timeout);
            abortController = null;
            await new Promise(r => setTimeout(r, RETRY_DELAY * (retryCount + 1)));
            return translateText(retryCount + 1);
        } else {
            outputText.textContent = "Erreur de traduction. Veuillez réessayer.";
        }
    } finally {
        clearTimeout(timeout);
        abortController = null;
        if (!retrying) finishTranslation();
    }

    const elapsed = ((performance.now() - t0) / 1000).toFixed(1);
    translationTime.textContent = `${elapsed}s`;

    if (fullText) {
        btnCopy.style.display = "flex";
        btnSpeak.style.display = "flex";
        addToHistory(text, fullText);
    }
}

function finishTranslation() {
    isTranslating = false;
    btnTranslate.disabled = false;
    btnTranslate.classList.remove("loading");
}

// Keyboard shortcut: Enter or Ctrl+Enter
inputText.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        translateText();
    }
});

btnTranslate.addEventListener("click", translateText);

// Clear
btnClear.addEventListener("click", () => {
    if (abortController) abortController.abort();
    inputText.value = "";
    outputText.innerHTML = '<span class="placeholder">La traduction apparaitra ici...</span>';
    charCount.textContent = "0";
    translationTime.textContent = "";
    btnCopy.style.display = "none";
    btnSpeak.style.display = "none";
    inputText.focus();
});

// Copy (with fallback for HTTP)
btnCopy.addEventListener("click", async () => {
    const text = outputText.textContent;
    if (!text) return;
    try {
        await navigator.clipboard.writeText(text);
    } catch {
        const ta = document.createElement("textarea");
        ta.value = text;
        Object.assign(ta.style, { position: "fixed", opacity: "0" });
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

// TTS
btnSpeak.addEventListener("click", () => {
    const text = outputText.textContent;
    if (!text) return;
    speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(text);
    utt.lang = isSpanish(inputText.value) ? "fr-FR" : "es-ES";
    utt.rate = 1.0;
    speechSynthesis.speak(utt);
});

// Language detection
const ES_REGEX = /[¿¡ñáéíóúü]|(\b(el|la|los|las|un|una|unos|unas|es|está|son|hola|como|qué|por|para|pero|con|sin|más|muy|también|tiene|hace|puede|esta|ese|esa|esto|aquí|ahora|donde|cuando|porque|si|no|ya|hay|ser|estar|tener|hacer|poder|decir|saber|querer|llegar|pasar|deber|poner|parecer|quedar|creer|hablar|llevar|dejar|seguir|encontrar|llamar|venir|pensar|salir|volver|tomar|conocer|vivir|sentir|tratar|mirar|contar|empezar|esperar|buscar|existir|entrar|trabajar|escribir|perder|producir|ocurrir|entender|pedir|recibir|recordar|terminar|permitir|aparecer|conseguir|comenzar|servir|sacar|necesitar|mantener|resultar|leer|caer|cambiar|presentar|crear|abrir|considerar|oír|acabar|convertir|ganar|formar)\b)/i;

function isSpanish(text) {
    return ES_REGEX.test(text);
}

// Voice input
const IS_ANDROID = /android/i.test(navigator.userAgent);

function initRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return null;
    const r = new SR();
    r.continuous = false;
    r.interimResults = !IS_ANDROID;
    r.lang = voiceLang === "es" ? "es-ES" : "fr-FR";
    r.maxAlternatives = 3; // More alternatives = better chance of correct transcription

    let restartCount = 0;
    const MAX_RESTARTS = 5;

    r.onresult = (e) => {
        const lastResult = e.results[e.results.length - 1];

        // Pick best alternative: highest confidence
        let bestTranscript = lastResult[0].transcript;
        let bestConfidence = lastResult[0].confidence || 0;
        for (let a = 1; a < lastResult.length; a++) {
            if (lastResult[a].confidence > bestConfidence) {
                bestConfidence = lastResult[a].confidence;
                bestTranscript = lastResult[a].transcript;
            }
        }

        inputText.value = bestTranscript;
        charCount.textContent = bestTranscript.length;
        recordingIndicator.querySelector("span").textContent =
            bestTranscript || (voiceLang === "es" ? "Escuchando..." : "Ecoute...");

        if (lastResult.isFinal) {
            stopRecording();
            // Auto-translate after short delay so user can see/correct the text
            setTimeout(() => translateText(), 600);
        }
    };

    r.onerror = (e) => {
        if (e.error === "no-speech" && isRecording && restartCount < MAX_RESTARTS) {
            restartCount++;
            setTimeout(() => { try { r.start(); } catch {} }, 300);
            return;
        }
        if (e.error === "not-allowed" || e.error === "service-not-available") {
            recordingIndicator.querySelector("span").textContent =
                "Micro non disponible";
            setTimeout(stopRecording, 1500);
            return;
        }
        stopRecording();
    };

    r.onend = () => {
        if (!isRecording) return;
        if (restartCount < MAX_RESTARTS) {
            restartCount++;
            setTimeout(() => { try { r.start(); } catch { stopRecording(); } }, 300);
        } else {
            stopRecording();
        }
    };

    return r;
}

function startRecording() {
    recognition = initRecognition();
    if (!recognition) {
        recordingIndicator.querySelector("span").textContent =
            "Navigateur non supporté";
        recordingIndicator.style.display = "flex";
        setTimeout(() => { recordingIndicator.style.display = "none"; }, 2000);
        return;
    }

    isRecording = true;
    btnMic.classList.add("active");
    recordingIndicator.style.display = "flex";
    recordingIndicator.querySelector("span").textContent =
        voiceLang === "es" ? "Escuchando..." : "Ecoute...";

    try {
        recognition.start();
    } catch {
        stopRecording();
    }
}

function stopRecording() {
    isRecording = false;
    btnMic.classList.remove("active");
    recordingIndicator.style.display = "none";
    if (recognition) { try { recognition.stop(); } catch {} }
}

// Mic: click + touch
btnMic.addEventListener("click", () => {
    isRecording ? stopRecording() : startRecording();
});

// Prevent double-tap zoom on mobile for mic button
btnMic.addEventListener("touchend", (e) => {
    e.preventDefault();
    btnMic.click();
}, { passive: false });

// History
function addToHistory(original, translated) {
    history = history.filter(h => h.original !== original);
    history.unshift({ original, translated, time: Date.now() });
    if (history.length > 20) history.length = 20;
    localStorage.setItem("trad_history", JSON.stringify(history));
    renderHistory();
}

function renderHistory() {
    const fragment = document.createDocumentFragment();
    const items = history.slice(0, 10);

    for (const h of items) {
        const li = document.createElement("li");
        const origShort = truncate(h.original, 40);
        const tradShort = truncate(h.translated, 40);
        const spanOrig = document.createElement("span");
        spanOrig.className = "original";
        spanOrig.textContent = origShort;

        const spanSep = document.createElement("span");
        spanSep.className = "sep";
        spanSep.textContent = "\u2192";

        const spanTrad = document.createElement("span");
        spanTrad.className = "translated";
        spanTrad.textContent = tradShort;

        li.appendChild(spanOrig);
        li.appendChild(spanSep);
        li.appendChild(spanTrad);
        li.addEventListener("click", () => {
            inputText.value = h.original;
            outputText.textContent = h.translated;
            outputText.classList.remove("placeholder");
            charCount.textContent = h.original.length;
            btnCopy.style.display = "flex";
            btnSpeak.style.display = "flex";
        });
        fragment.appendChild(li);
    }

    historyList.innerHTML = "";
    historyList.appendChild(fragment);
}

function truncate(s, max) {
    return s.length > max ? s.slice(0, max) + "..." : s;
}

btnClearHistory.addEventListener("click", () => {
    history = [];
    localStorage.removeItem("trad_history");
    renderHistory();
});

// Init
renderHistory();
