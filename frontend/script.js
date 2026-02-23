/* ─── Healthcare Chatbot v3 — Frontend Logic ────────────────── */

const API_BASE = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? "http://localhost:8000"
  : window.location.origin;

// Use streaming only on localhost; Vercel serverless doesn't support SSE reliably
const IS_PRODUCTION = !(window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");
const SESSION_ID = crypto.randomUUID();
const CHAT_STORAGE_KEY = "medassist_chat_history";

// ─── DOM ─────────────────────────────────────────────────────
const disclaimerModal = document.getElementById("disclaimerModal");
const acceptBtn = document.getElementById("acceptBtn");
const appContainer = document.getElementById("appContainer");
const chatArea = document.getElementById("chatArea");
const welcomeScreen = document.getElementById("welcomeScreen");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");
const uploadBtn = document.getElementById("uploadBtn");
const fileInput = document.getElementById("fileInput");
const attachedFile = document.getElementById("attachedFile");
const attachedFileName = document.getElementById("attachedFileName");
const removeFileBtn = document.getElementById("removeFileBtn");
const symptomBtn = document.getElementById("symptomBtn");
const drugInteractionBtn = document.getElementById("drugInteractionBtn");
const symptomModal = document.getElementById("symptomModal");
const drugModal = document.getElementById("drugModal");
const langSelect = document.getElementById("langSelect");
const hospitalBtn = document.getElementById("hospitalBtn");
const hospitalPanel = document.getElementById("hospitalPanel");
const hospitalList = document.getElementById("hospitalList");
const exportBtn = document.getElementById("exportBtn");
const newChatBtn = document.getElementById("newChatBtn");
const profileBadge = document.getElementById("profileBadge");
const profileTags = document.getElementById("profileTags");
const labBadge = document.getElementById("labBadge");
const labBadgeText = document.getElementById("labBadgeText");

let isWaiting = false;
let currentProfile = {};
let chatMessages = []; // For PDF export

// ─── Disclaimer ──────────────────────────────────────────────
acceptBtn.addEventListener("click", () => {
    disclaimerModal.style.display = "none";
    appContainer.style.display = "flex";
    loadChatHistory();
    messageInput.focus();
});

// ─── New Chat ────────────────────────────────────────────────
newChatBtn.addEventListener("click", () => {
    localStorage.removeItem(CHAT_STORAGE_KEY);
    chatMessages = [];
    currentProfile = {};
    profileBadge.style.display = "none";
    profileTags.innerHTML = "";
    chatArea.innerHTML = "";
    // Recreate welcome screen
    const ws = document.createElement("div");
    ws.className = "welcome-screen";
    ws.id = "welcomeScreen";
    ws.innerHTML = `
        <div class="welcome-icon">💬</div>
        <h2>How can I help you today?</h2>
        <p>Ask about health topics, symptoms, medicines, upload a report, or use voice input.</p>
        <div class="suggestion-chips">
            <button class="chip" data-query="What is diabetes?">What is diabetes?</button>
            <button class="chip" data-query="Symptoms of high blood pressure">High blood pressure</button>
            <button class="chip" data-query="What medicine can I take for a headache?">Medicine for headache</button>
            <button class="chip" data-query="How to prevent heart disease?">Heart disease prevention</button>
        </div>
    `;
    chatArea.appendChild(ws);
    bindChips();
    messageInput.focus();
});

// ─── Chips ───────────────────────────────────────────────────
function bindChips() {
    document.querySelectorAll(".chip[data-query]").forEach(chip => {
        chip.addEventListener("click", () => { messageInput.value = chip.getAttribute("data-query"); sendMessage(); });
    });
}
bindChips();

// ─── Send ────────────────────────────────────────────────────
sendBtn.addEventListener("click", sendMessage);
messageInput.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });

async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text || isWaiting) return;
    const ws = document.getElementById("welcomeScreen");
    if (ws) ws.style.display = "none";

    // Show file name alongside user message if attached
    const fileLabel = attachedFileName.textContent ? ` [${attachedFileName.textContent}]` : "";
    appendMessage("user", text + fileLabel);
    chatMessages.push({ role: "user", text: text + fileLabel, time: new Date().toLocaleTimeString() });
    saveChatMessage("user", text + fileLabel);
    messageInput.value = "";
    // Clear doc attachment after sending
    attachedFile.style.display = "none";
    attachedFileName.textContent = "";
    labBadge.style.display = "none";
    isWaiting = true;
    sendBtn.disabled = true;

    const typingEl = showTypingIndicator();
    const lang = langSelect.value;

    try {
        if (IS_PRODUCTION) {
            // ── Sync mode (Vercel) ──────────────────────────────────────
            const resp = await fetch(`${API_BASE}/chat/sync`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text, session_id: SESSION_ID, language: lang }),
            });
            if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
            typingEl.remove();

            const data = await resp.json();
            const { bubbleEl, sourcesContainer, followupContainer, translatedContainer } = appendBotMessageContainer();

            if (data.emergency) showEmergencyAlert(data.emergency);
            if (data.profile) updateProfileBadge(data.profile);

            const { cleanText, followups } = extractFollowups(data.response || "");
            bubbleEl.innerHTML = renderMarkdown(cleanText);
            addMedicalTooltips(bubbleEl);
            if (data.sources && data.sources.length > 0) renderSources(sourcesContainer, data.sources);
            if (followups.length > 0) renderFollowups(followupContainer, followups);
            chatMessages.push({ role: "bot", text: cleanText, time: new Date().toLocaleTimeString() });
            saveChatMessage("bot", cleanText);
            scrollToBottom();

        } else {
            // ── Streaming mode (localhost) ──────────────────────────────
            const resp = await fetch(`${API_BASE}/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text, session_id: SESSION_ID, language: lang }),
            });
            if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
            typingEl.remove();

            const { bubbleEl, sourcesContainer, followupContainer, translatedContainer } = appendBotMessageContainer();
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let fullResponse = "";
            let sources = [];

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                for (const line of chunk.split("\n")) {
                    if (!line.startsWith("data: ")) continue;
                    const jsonStr = line.slice(6).trim();
                    if (!jsonStr) continue;
                    try {
                        const data = JSON.parse(jsonStr);
                        if (data.type === "emergency") { showEmergencyAlert(data.content); }
                        else if (data.type === "profile") { updateProfileBadge(data.profile); }
                        else if (data.type === "token") {
                            fullResponse += data.content;
                            bubbleEl.innerHTML = renderMarkdown(fullResponse);
                            addMedicalTooltips(bubbleEl);
                            scrollToBottom();
                        } else if (data.type === "translated") {
                            renderTranslated(translatedContainer, data.content);
                        } else if (data.type === "sources") { sources = data.sources || []; }
                        else if (data.type === "done") {
                            const { cleanText, followups } = extractFollowups(fullResponse);
                            bubbleEl.innerHTML = renderMarkdown(cleanText);
                            addMedicalTooltips(bubbleEl);
                            if (sources.length > 0) renderSources(sourcesContainer, sources);
                            if (followups.length > 0) renderFollowups(followupContainer, followups);
                            chatMessages.push({ role: "bot", text: cleanText, time: new Date().toLocaleTimeString() });
                            saveChatMessage("bot", cleanText);
                        } else if (data.type === "error") { bubbleEl.innerHTML = `<em>Error: ${data.content}</em>`; }
                    } catch (e) { }
                }
            }
        }
    } catch (err) {
        typingEl.remove();
        appendMessage("bot", `Sorry, I couldn't process your request.\n\n*Error: ${err.message}*`);
    }
    isWaiting = false;
    sendBtn.disabled = false;
    messageInput.focus();
}

// ─── Emergency Alert ─────────────────────────────────────────
function showEmergencyAlert(content) {
    const div = document.createElement("div");
    div.className = "emergency-alert";
    div.innerHTML = renderMarkdown(content);
    chatArea.appendChild(div);
    scrollToBottom();
}

// ─── Follow-ups ──────────────────────────────────────────────
function extractFollowups(text) {
    // Match both [FOLLOWUP: ...] and bare FOLLOWUP: ... (LLM sometimes drops brackets)
    let match = text.match(/\[FOLLOWUP:\s*(.+?)\]/i);
    if (!match) match = text.match(/FOLLOWUP:\s*(.+?)$/im);
    if (!match) return { cleanText: text, followups: [] };
    const cleanText = text
        .replace(/\[FOLLOWUP:\s*.+?\]/i, "")
        .replace(/FOLLOWUP:\s*.+$/im, "")
        .trim();
    const followups = match[1].split("|").map(q => q.trim()).filter(q => q);
    return { cleanText, followups };
}
function renderFollowups(container, followups) {
    const div = document.createElement("div"); div.className = "followup-chips";
    for (const q of followups) {
        const chip = document.createElement("button"); chip.className = "followup-chip"; chip.textContent = q;
        chip.addEventListener("click", () => { messageInput.value = q; sendMessage(); });
        div.appendChild(chip);
    }
    container.appendChild(div); scrollToBottom();
}

// ─── Translated Response ─────────────────────────────────────
function renderTranslated(container, text) {
    const langName = langSelect.options[langSelect.selectedIndex].text;
    const div = document.createElement("div"); div.className = "translated-bubble";
    div.innerHTML = `<div class="translated-label">🌐 ${langName}</div>${renderMarkdown(text)}`;
    container.appendChild(div); scrollToBottom();
}

// ─── Profile Badge ───────────────────────────────────────────
function updateProfileBadge(profile) {
    currentProfile = profile;
    if (Object.keys(profile).length === 0) { profileBadge.style.display = "none"; return; }
    profileBadge.style.display = "flex";
    profileTags.innerHTML = Object.entries(profile)
        .map(([k, v]) => `<span class="profile-tag">#${k}: ${v}</span>`).join(" ");
}

// ─── Medical Tooltips ────────────────────────────────────────
function addMedicalTooltips(element) {
    if (typeof MEDICAL_TERMS === "undefined") return;
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, null, false);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    for (const node of textNodes) {
        let html = node.textContent; let changed = false;
        for (const [term, def] of Object.entries(MEDICAL_TERMS)) {
            const rx = new RegExp(`\\b(${term})\\b`, "gi");
            if (rx.test(html)) { html = html.replace(rx, `<span class="med-tooltip">$1<span class="tooltip-text">${def}</span></span>`); changed = true; }
        }
        if (changed) { const s = document.createElement("span"); s.innerHTML = html; node.parentNode.replaceChild(s, node); }
    }
}

// ─── Voice Input ─────────────────────────────────────────────
let recognition = null, isRecording = false;
if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SR(); recognition.continuous = false; recognition.interimResults = false; recognition.lang = "en-US";
    recognition.onresult = e => { messageInput.value = e.results[0][0].transcript; stopRec(); sendMessage(); };
    recognition.onerror = () => stopRec(); recognition.onend = () => stopRec();
}
micBtn.addEventListener("click", () => {
    if (!recognition) { alert("Voice not supported."); return; }
    if (isRecording) { recognition.stop(); stopRec(); } else { recognition.start(); isRecording = true; micBtn.classList.add("recording"); micBtn.textContent = "⏹"; }
});
function stopRec() { isRecording = false; micBtn.classList.remove("recording"); micBtn.textContent = "🎙️"; }

// ─── File Upload ─────────────────────────────────────────────
uploadBtn.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", async e => {
    const file = e.target.files[0]; if (!file) return;
    attachedFile.style.display = "flex";
    attachedFileName.textContent = `📄 ${file.name}`;
    const formData = new FormData(); formData.append("file", file);
    try {
        const resp = await fetch(`${API_BASE}/upload`, { method: "POST", body: formData });
        const data = await resp.json();
        if (data.lab_findings && data.lab_findings.length > 0) {
            labBadge.style.display = "block";
            const abnormal = data.lab_findings.filter(f => f.status !== "NORMAL").length;
            labBadgeText.textContent = `🧪 ${data.lab_findings.length} values detected, ${abnormal} abnormal`;
        }
    } catch (err) { console.error("Upload error:", err); }
    fileInput.value = "";
});
removeFileBtn.addEventListener("click", () => {
    attachedFile.style.display = "none"; attachedFileName.textContent = "";
    labBadge.style.display = "none";
});

// ─── Symptom Checker ─────────────────────────────────────────
symptomBtn.addEventListener("click", () => { symptomModal.style.display = "flex"; });
function closeSymptomModal() { symptomModal.style.display = "none"; }
function nextSymptomStep(s) { document.querySelectorAll(".symptom-step").forEach(el => el.style.display = "none"); document.querySelector(`.symptom-step[data-step="${s}"]`).style.display = "block"; }
function submitSymptomChecker() {
    const age = document.getElementById("symAge").value, gender = document.getElementById("symGender").value;
    const primary = document.getElementById("symPrimary").value, duration = document.getElementById("symDuration").value;
    const severity = document.getElementById("symSeverity").value, other = document.getElementById("symOther").value;
    if (!primary) { alert("Enter your primary symptom."); return; }
    const q = `I am a ${age} year old ${gender}. My primary symptom is ${primary}. I've had it for ${duration}. Severity: ${severity}. ${other ? `Other symptoms: ${other}. ` : ""}What could this be and what should I do?`;
    closeSymptomModal(); messageInput.value = q; nextSymptomStep(1); sendMessage();
}

// ─── Drug Interaction ────────────────────────────────────────
drugInteractionBtn.addEventListener("click", () => { drugModal.style.display = "flex"; });
function closeDrugModal() { drugModal.style.display = "none"; }
function checkDrugInteraction() {
    const d1 = document.getElementById("drug1Input").value.trim(), d2 = document.getElementById("drug2Input").value.trim();
    if (!d1 || !d2) { alert("Enter both drug names."); return; }
    closeDrugModal(); messageInput.value = `What are the drug interactions between ${d1} and ${d2}?`;
    document.getElementById("drug1Input").value = ""; document.getElementById("drug2Input").value = "";
    sendMessage();
}

// ─── Hospital Finder (Overpass API / OpenStreetMap) ──────────
hospitalBtn.addEventListener("click", () => {
    hospitalPanel.style.display = "flex";
    hospitalList.innerHTML = '<p class="hospital-loading">📍 Detecting your location...</p>';
    if (!navigator.geolocation) { hospitalList.innerHTML = '<p class="hospital-loading">⚠️ Geolocation not supported.</p>'; return; }
    navigator.geolocation.getCurrentPosition(pos => {
        const { latitude: lat, longitude: lon } = pos.coords;
        findHospitals(lat, lon);
    }, () => { hospitalList.innerHTML = '<p class="hospital-loading">⚠️ Location access denied.</p>'; });
});
function closeHospitalPanel() { hospitalPanel.style.display = "none"; }

async function findHospitals(lat, lon) {
    hospitalList.innerHTML = '<p class="hospital-loading">🔍 Searching nearby hospitals...</p>';
    const radius = 5000; // 5km
    const query = `[out:json][timeout:10];(node["amenity"="hospital"](around:${radius},${lat},${lon});way["amenity"="hospital"](around:${radius},${lat},${lon}););out center 15;`;
    try {
        const resp = await fetch("https://overpass-api.de/api/interpreter", {
            method: "POST", body: `data=${encodeURIComponent(query)}`,
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
        });
        const data = await resp.json();
        const elements = data.elements || [];
        if (elements.length === 0) { hospitalList.innerHTML = '<p class="hospital-loading">No hospitals found within 5km.</p>'; return; }

        hospitalList.innerHTML = "";
        for (const el of elements.slice(0, 15)) {
            const name = el.tags?.name || "Hospital";
            const elLat = el.lat || el.center?.lat;
            const elLon = el.lon || el.center?.lon;
            const dist = elLat ? calcDistance(lat, lon, elLat, elLon) : null;
            const card = document.createElement("div"); card.className = "hospital-card";
            card.innerHTML = `<h4>${name}</h4>${dist ? `<p>📍 ${dist.toFixed(1)} km away</p>` : ""}${elLat ? `<a href="https://www.google.com/maps/dir/?api=1&destination=${elLat},${elLon}" target="_blank" rel="noopener">Get Directions →</a>` : ""}`;
            hospitalList.appendChild(card);
        }
    } catch (err) { hospitalList.innerHTML = `<p class="hospital-loading">⚠️ Error: ${err.message}</p>`; }
}

function calcDistance(lat1, lon1, lat2, lon2) {
    const R = 6371, dLat = (lat2 - lat1) * Math.PI / 180, dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ─── Export Chat as PDF ──────────────────────────────────────
exportBtn.addEventListener("click", exportChatPDF);
function exportChatPDF() {
    if (chatMessages.length === 0) { alert("No messages to export."); return; }
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF();
    let y = 20;

    doc.setFontSize(18); doc.setTextColor(93, 211, 182);
    doc.text("MedAssist — Health Consultation Report", 14, y); y += 10;
    doc.setFontSize(9); doc.setTextColor(110, 80, 52);
    doc.text(`Generated: ${new Date().toLocaleString()}  |  Session: ${SESSION_ID.slice(0, 8)}`, 14, y); y += 8;

    // Profile
    if (Object.keys(currentProfile).length > 0) {
        doc.setFontSize(11); doc.setTextColor(66, 184, 156);
        doc.text("Patient Profile", 14, y); y += 6;
        doc.setFontSize(9); doc.setTextColor(58, 46, 34);
        for (const [k, v] of Object.entries(currentProfile)) {
            doc.text(`#${k}: ${v}`, 18, y); y += 5;
        }
        y += 4;
    }

    // Disclaimer
    doc.setFontSize(8); doc.setTextColor(150, 130, 112);
    doc.text("Disclaimer: This report is for informational purposes only and is NOT medical advice.", 14, y); y += 8;
    doc.setDrawColor(205, 184, 133); doc.line(14, y, 196, y); y += 6;

    // Messages
    for (const msg of chatMessages) {
        if (y > 270) { doc.addPage(); y = 20; }
        doc.setFontSize(8); doc.setTextColor(150, 130, 112);
        doc.text(`[${msg.time}] ${msg.role === "user" ? "You" : "MedAssist"}`, 14, y); y += 5;
        doc.setFontSize(10); doc.setTextColor(58, 46, 34);
        const lines = doc.splitTextToSize(msg.text || "", 178);
        for (const line of lines) {
            if (y > 280) { doc.addPage(); y = 20; }
            doc.text(line, 18, y); y += 5;
        }
        y += 4;
    }

    doc.save("MedAssist_Report.pdf");
}

// ─── Chat Persistence ───────────────────────────────────────
function saveChatMessage(role, text) {
    try {
        const h = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || "[]");
        h.push({ role, text, time: Date.now() });
        if (h.length > 50) h.splice(0, h.length - 50);
        localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(h));
    } catch (e) { }
}
function loadChatHistory() {
    try {
        const h = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || "[]");
        const ws = document.getElementById("welcomeScreen");
        if (h.length > 0 && ws) {
            ws.style.display = "none";
            for (const m of h) appendMessage(m.role === "bot" ? "bot" : "user", m.text, false);
        }
    } catch (e) { }
}

// ─── UI Helpers ──────────────────────────────────────────────
function appendMessage(role, text, animate = true) {
    const div = document.createElement("div"); div.className = `message ${role}`;
    if (!animate) div.style.animation = "none";
    const av = document.createElement("div"); av.className = "message-avatar"; av.textContent = role === "user" ? "👤" : "🩺";
    const bb = document.createElement("div"); bb.className = "message-bubble";
    bb.innerHTML = role === "bot" ? renderMarkdown(text) : escapeHtml(text);
    if (role === "bot") addMedicalTooltips(bb);
    div.appendChild(av); div.appendChild(bb); chatArea.appendChild(div); scrollToBottom();
}
function appendBotMessageContainer() {
    const div = document.createElement("div"); div.className = "message bot";
    const av = document.createElement("div"); av.className = "message-avatar"; av.textContent = "🩺";
    const wrap = document.createElement("div");
    const bb = document.createElement("div"); bb.className = "message-bubble";
    const sc = document.createElement("div"), fc = document.createElement("div"), tc = document.createElement("div");
    wrap.appendChild(bb); wrap.appendChild(tc); wrap.appendChild(sc); wrap.appendChild(fc);
    div.appendChild(av); div.appendChild(wrap); chatArea.appendChild(div); scrollToBottom();
    return { bubbleEl: bb, sourcesContainer: sc, followupContainer: fc, translatedContainer: tc };
}
function showTypingIndicator() {
    const div = document.createElement("div"); div.className = "message bot";
    const av = document.createElement("div"); av.className = "message-avatar"; av.textContent = "🩺";
    const ind = document.createElement("div"); ind.className = "message-bubble typing-indicator";
    ind.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
    div.appendChild(av); div.appendChild(ind); chatArea.appendChild(div); scrollToBottom();
    return div;
}
function renderSources(container, sources) {
    const unique = []; const seen = new Set();
    for (const s of sources) { if (!seen.has(s.title)) { seen.add(s.title); unique.push(s); } }
    if (!unique.length) return;
    const d = document.createElement("div"); d.className = "sources-container";
    const l = document.createElement("div"); l.className = "sources-label"; l.textContent = "📚 Sources"; d.appendChild(l);
    for (const s of unique) { const a = document.createElement("a"); a.className = "source-link"; a.href = s.url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = `↗ ${s.title}`; d.appendChild(a); }
    container.appendChild(d); scrollToBottom();
}
function scrollToBottom() { chatArea.scrollTop = chatArea.scrollHeight; }

// ─── Markdown ────────────────────────────────────────────────
function renderMarkdown(text) {
    let h = escapeHtml(text);
    h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/\*(.+?)\*/g, "<em>$1</em>");
    h = h.replace(/^[-•]\s+(.+)$/gm, "<li>$1</li>");
    h = h.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");
    h = h.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");
    h = h.replace(/((?:<li>.*<\/li>\n?)+)/g, m => m.startsWith("<ul>") ? m : `<ol>${m}</ol>`);
    h = h.split("\n\n").map(p => `<p>${p.trim()}</p>`).join("");
    h = h.replace(/\n/g, "<br>");
    return h;
}
function escapeHtml(text) { const d = document.createElement("div"); d.textContent = text; return d.innerHTML; }
