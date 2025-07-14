// ===== CONFIGURATION =====
const sessionId = document.getElementById('session-id')?.value || '';
const chatBox = document.getElementById('chat-box');
const modal = document.getElementById("message-modal");

// Global state
let chatMessages = [];
let currentMessage = null;

// ===== UTILITY FUNCTIONS =====
function getSelectedReasons() {
    return Array.from(document.querySelectorAll('#moderation-reason input[type="checkbox"]:checked'))
        .map(cb => cb.value);
}

function clearReasonCheckboxes() {
    document.querySelectorAll('#moderation-reason input[type="checkbox"]')
        .forEach(cb => cb.checked = false);
}

function formatReasons(message) {
    if (message.reasons && message.reasons.length > 0) {
        return message.reasons.join(', ');
    }
    return message.reason || 'Moderado';
}

// ===== MESSAGE DISPLAY =====
function createMessageElement(message) {
    const messageElement = document.createElement("p");
    messageElement.style.cursor = "pointer";
    const timestampWithoutSeconds = message.timestamp.substring(0, 5);
    
    if (message.moderated) {
        messageElement.classList.add("moderated", "blurred");
        messageElement.textContent = `${timestampWithoutSeconds} ${message.username}: [Moderado] Click para ver`;
    } else {
        messageElement.textContent = `${timestampWithoutSeconds} ${message.username}: ${message.text}`;
    }
    
    messageElement.addEventListener("click", () => openModal(message));
    return messageElement;
}

function addNewMessage(message) {
    // Check for duplicates
    const isDuplicate = chatMessages.some(msg => 
        msg.username === message.username && 
        msg.timestamp === message.timestamp && 
        msg.text === message.text
    );
    
    if (isDuplicate) return;
    
    // Add to store and display
    chatMessages.push(message);
    const messageElement = createMessageElement(message);
    chatBox.appendChild(messageElement);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function refreshChatDisplay() {
    chatBox.innerHTML = '';
    chatMessages.forEach(message => {
        const messageElement = createMessageElement(message);
        chatBox.appendChild(messageElement);
    });
    chatBox.scrollTop = chatBox.scrollHeight;
}

// ===== MODAL FUNCTIONS =====
function openModal(message) {
    currentMessage = message;
    
    // Update modal content
    document.getElementById("modal-message").textContent = message.text;
    document.getElementById("modal-user").textContent = message.username;
    document.getElementById("modal-time").textContent = message.timestamp;
    document.getElementById("modal-reason").textContent = message.moderated 
        ? `Razones: ${formatReasons(message)}` 
        : "No moderado";
    
    // Update button visibility
    updateModalButtons(message.moderated);
    
    // Show modal
    modal.classList.remove("hidden");
}

function closeModal() {
    modal.classList.add("hidden");
    clearReasonCheckboxes();
    currentMessage = null;
}

function updateModalButtons(isModerated) {
    const moderateBtn = document.getElementById("moderate-btn");
    const unmoderateBtn = document.getElementById("unmoderate-btn");
    const reasonSection = document.getElementById("moderation-reason");
    
    if (isModerated) {
        moderateBtn.style.display = 'none';
        unmoderateBtn.style.display = 'inline-block';
        reasonSection.style.display = 'none';
    } else {
        moderateBtn.style.display = 'inline-block';
        unmoderateBtn.style.display = 'none';
        reasonSection.style.display = 'block';
    }
}

// ===== MODERATION FUNCTIONS =====
async function moderateMessage() {
    if (!currentMessage) return;
    
    const reasons = getSelectedReasons();
    if (reasons.length === 0) {
        alert("Seleccione al menos una razón");
        return;
    }
    
    await toggleModeration('moderate', reasons);
}

async function unmoderateMessage() {
    if (!currentMessage) return;
    await toggleModeration('unmoderate');
}

async function toggleModeration(action, reasons = []) {
    try {
        const response = await fetch(`${window.location}/toggle_moderation`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': sessionId
            },
            body: JSON.stringify({
                username: currentMessage.username,
                timestamp: currentMessage.timestamp,
                text: currentMessage.text,
                reasons: reasons.length > 0 ? reasons : undefined
            })
        });

        const data = await response.json();
        
        if (data.status === 'success') {
            updateMessageStatus(data.action, reasons);
            refreshChatDisplay();
            closeModal();
        } else {
            console.error('Failed to toggle moderation:', data);
            alert('Error al procesar la moderación');
        }
    } catch (error) {
        console.error('Error toggling moderation:', error);
        alert('Error de conexión');
    }
}

function updateMessageStatus(action, reasons) {
    const messageIndex = chatMessages.findIndex(msg => 
        msg.username === currentMessage.username && 
        msg.timestamp === currentMessage.timestamp && 
        msg.text === currentMessage.text
    );
    
    if (messageIndex !== -1) {
        chatMessages[messageIndex].moderated = action === 'moderated';
        
        if (action === 'moderated' && reasons.length > 0) {
            chatMessages[messageIndex].reasons = reasons;
            chatMessages[messageIndex].reason = reasons[0]; // Backward compatibility
        } else if (action === 'unmoderated') {
            delete chatMessages[messageIndex].reasons;
            delete chatMessages[messageIndex].reason;
        }
    }
}

// ===== EVENT SOURCE SETUP =====
function initializeEventSource() {
    const evtSource = new EventSource(`${window.location}`);
    
    evtSource.onmessage = function(event) {
        const message = JSON.parse(event.data);
        addNewMessage(message);
    };
    
    evtSource.onerror = function(event) {
        console.error('EventSource failed:', event);
    };
    
    // Clean up on page unload
    window.addEventListener('beforeunload', () => evtSource.close());
    
    return evtSource;
}

// ===== EVENT LISTENERS =====
function setupEventListeners() {
    // Modal close button
    const closeBtn = document.querySelector(".close-btn");
    if (closeBtn) {
        closeBtn.onclick = closeModal;
    }
    
    // Click outside modal to close
    window.onclick = function(event) {
        if (event.target === modal) {
            closeModal();
        }
    };
    
    // Moderation buttons
    const moderateBtn = document.getElementById("moderate-btn");
    const unmoderateBtn = document.getElementById("unmoderate-btn");
    
    if (moderateBtn) {
        moderateBtn.onclick = moderateMessage;
    }
    
    if (unmoderateBtn) {
        unmoderateBtn.onclick = unmoderateMessage;
    }
}

// ===== INITIALIZATION =====
document.addEventListener('DOMContentLoaded', function() {
    setupEventListeners();
    initializeEventSource();
});