// ===== CONFIGURATION & GLOBAL STATE =====
const sessionId = document.getElementById('session-id')?.value || '';
const chatBox = document.getElementById('chat-box');
const modal = document.getElementById("message-modal");
const channelName = document.getElementById('channel-name')?.value || '';
const embedButton = document.getElementById("embed-chat-btn");
const copyLinkButton = document.getElementById("copy-embed-link-btn");

// Store all messages and current modal state
let chatMessages = [];
let currentMessage = null;

// Default moderation reasons for filtering display
const DEFAULT_REASONS = new Set([
    'Garabato', 'Spam', 'Racismo/Xenofobia', 'Homofobia', 'Contenido sexual',
    'Insulto', 'Machismo/Misoginia/Sexismo', 'Divulgación de información personal (doxxing)',
    'Otros', 'Amenaza/acoso violento', 'No baneable'
]);

if (typeof window.selectedReasons === 'undefined') {
    window.selectedReasons = new Set(DEFAULT_REASONS);
}

// ===== UTILITY FUNCTIONS =====
function getSelectedReasons() {
    const checkboxes = document.querySelectorAll('#moderation-reason input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

function clearReasonCheckboxes() {
    const checkboxes = document.querySelectorAll('#moderation-reason input[type="checkbox"]');
    checkboxes.forEach(cb => cb.checked = false);
}

function getDisplayReason(message) {
    if (message.reasons && Array.isArray(message.reasons) && message.reasons.length > 0) {
        return message.reasons.join(', ');
    }
    return message.reason || 'Moderado';
}

function shouldShowMessage(message) {
    // Always show unmoderated messages
    if (!message.moderated) return true;
    
    // For moderated messages, check if any reason is selected for display
    if (message.reasons && Array.isArray(message.reasons)) {
        return message.reasons.some(reason => window.selectedReasons.has(reason));
    }
    
    // Backward compatibility for single reason
    if (message.reason) {
        return window.selectedReasons.has(message.reason);
    }
    
    return false;
}

// ===== MESSAGE DISPLAY FUNCTIONS =====
function createMessageElement(message) {
    const msgElement = document.createElement("p");
    msgElement.style.cursor = "pointer";
    
    const isModeratedAndVisible = message.moderated && shouldShowMessage(message);
    
    if (isModeratedAndVisible) {
        // Show as moderated (blurred with reason)
        msgElement.classList.add("moderated", "blurred");
        const displayReason = getDisplayReason(message);
        msgElement.innerHTML = `<strong>${message.timestamp} - ${message.username}:</strong> [${displayReason}] Click to view`;
    } else {
        // Show as normal message
        msgElement.innerHTML = `<strong>${message.timestamp} - ${message.username}:</strong> ${message.text}`;
    }
    
    // Add click handler to open modal
    msgElement.addEventListener("click", () => openMessageModal(message));
    
    return msgElement;
}

function refreshChatDisplay() {
    chatBox.innerHTML = '';
    
    chatMessages.forEach(message => {
        const msgElement = createMessageElement(message);
        chatBox.appendChild(msgElement);
    });
    
    chatBox.scrollTop = chatBox.scrollHeight;
}

function addNewMessage(messageData) {
    // Check for duplicates
    const isDuplicate = chatMessages.some(msg => 
        msg.username === messageData.username && 
        msg.timestamp === messageData.timestamp && 
        msg.text === messageData.text
    );
    
    if (isDuplicate) return;
    
    // Add to store and display
    chatMessages.push(messageData);
    const msgElement = createMessageElement(messageData);
    chatBox.appendChild(msgElement);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// ===== MODAL FUNCTIONS =====
function openMessageModal(message) {
    currentMessage = message;
    
    // Update modal content
    document.getElementById("modal-message").textContent = message.text;
    document.getElementById("modal-reason").textContent = message.moderated ? getDisplayReason(message) : "No moderado";
    document.getElementById("modal-user").textContent = message.username;
    document.getElementById("modal-time").textContent = message.timestamp;
    
    // Update button visibility
    updateModalButtons(message);
    
    // Show modal
    modal.classList.remove("hidden");
}

function closeMessageModal() {
    modal.classList.add("hidden");
    clearReasonCheckboxes();
    currentMessage = null;
}

function updateModalButtons(message) {
    const moderateBtn = document.getElementById("moderate-btn");
    const unmoderateBtn = document.getElementById("unmoderate-btn");
    const reasonSelect = document.getElementById("moderation-reason");
    
    if (message.moderated) {
        moderateBtn.style.display = 'none';
        unmoderateBtn.style.display = 'inline-block';
        reasonSelect.style.display = 'none';
    } else {
        moderateBtn.style.display = 'inline-block';
        unmoderateBtn.style.display = 'none';
        reasonSelect.style.display = 'block';
    }
}

// ===== MODERATION FUNCTIONS =====
async function toggleModeration(message, reasons = null) {
    // Validate that reasons are provided when moderating
    if (!message.moderated && (!reasons || reasons.length === 0)) {
        alert("Por favor seleccione una razón para moderar el mensaje");
        return;
    }

    try {
        const response = await fetch(window.location + '/toggle_moderation', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': sessionId
            },
            body: JSON.stringify({
                username: message.username,
                timestamp: message.timestamp,
                text: message.text,
                reasons: reasons || (message.reasons || [message.reason].filter(Boolean))
            })
        });
        
        if (!response.ok) {
            console.error('Failed to toggle moderation status');
            return;
        }
        
        const data = await response.json();
        if (data.status === 'success') {
            updateMessageModerationStatus(message, data.action, reasons);
            refreshChatDisplay();
            updateModalButtons(currentMessage);
            clearReasonCheckboxes();
        }
    } catch (error) {
        console.error('Error toggling moderation status:', error);
    }
}

function updateMessageModerationStatus(message, action, reasons) {
    const messageIndex = chatMessages.findIndex(msg => 
        msg.username === message.username && 
        msg.timestamp === message.timestamp && 
        msg.text === message.text
    );
    
    if (messageIndex === -1) return;
    
    // Update message in store
    chatMessages[messageIndex].moderated = action === 'moderated';
    
    if (action === 'moderated' && reasons) {
        chatMessages[messageIndex].reasons = reasons;
        chatMessages[messageIndex].reason = reasons[0]; // Backward compatibility
    } else if (action === 'unmoderated') {
        delete chatMessages[messageIndex].reasons;
        delete chatMessages[messageIndex].reason;
    }
    
    // Update current message if it's the same one
    if (currentMessage && 
        currentMessage.username === message.username &&
        currentMessage.timestamp === message.timestamp &&
        currentMessage.text === message.text) {
        currentMessage = chatMessages[messageIndex];
    }
}

// ===== FILTER FUNCTIONS =====
async function updateModerationReasons(reasons) {
    try {
        const response = await fetch(window.location + '/update_reasons', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': sessionId
            },
            body: JSON.stringify({ reasons: Array.from(reasons) })
        });
        
        if (!response.ok) {
            console.error('Failed to update moderation reasons');
        }
    } catch (error) {
        console.error('Error updating moderation reasons:', error);
    }
}

window.updateSelectedReasons = function(reason, isChecked) {
    if (isChecked) {
        window.selectedReasons.add(reason);
    } else {
        window.selectedReasons.delete(reason);
    }
    updateModerationReasons(window.selectedReasons);
    refreshChatDisplay();
};

// ===== EVENT SOURCE SETUP =====
function initializeEventSource() {
    const evtSource = new EventSource(window.location + `/chat?session_id=${sessionId}`);
    
    evtSource.onmessage = function(event) {
        const messageData = JSON.parse(event.data);
        addNewMessage(messageData);
    };
    
    evtSource.onerror = function(event) {
        console.error('EventSource failed:', event);
        // Could implement reconnection logic here
    };
    
    // Clean up on page unload
    window.addEventListener('beforeunload', function() {
        evtSource.close();
    });
    
    return evtSource;
}

// ===== EVENT LISTENERS SETUP =====
function setupEventListeners() {
    // Modal close button
    const closeBtn = document.querySelector(".close-btn");
    if (closeBtn) {
        closeBtn.onclick = closeMessageModal;
    }
    
    // Click outside modal to close
    window.onclick = function(event) {
        if (event.target === modal) {
            closeMessageModal();
        }
    };
    
    // Moderate button
    const moderateBtn = document.getElementById("moderate-btn");
    if (moderateBtn) {
        moderateBtn.addEventListener('click', () => {
            if (!currentMessage) return;
            
            const selectedReasons = getSelectedReasons();
            if (selectedReasons.length > 0) {
                toggleModeration(currentMessage, selectedReasons);
                closeMessageModal();
            } else {
                alert("Por favor seleccione una razón para moderar el mensaje");
            }
        });
    }
    
    // Unmoderate button
    const unmoderateBtn = document.getElementById("unmoderate-btn");
    if (unmoderateBtn) {
        unmoderateBtn.addEventListener('click', () => {
            if (currentMessage) {
                toggleModeration(currentMessage);
            }
        });
    }
    
    // Checkbox event listeners (for logging/debugging)
    const checkboxes = document.querySelectorAll('#moderation-reason input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            console.log('Checkbox changed:', this.value, this.checked);
        });
    });
}

// ===== EMBED CHAT BUTTON =====
embedButton?.addEventListener("click", function() {
    const embedUrl = `${window.location}/embed-chat/${channelName}?session_id=${sessionId}`;
    window.open(embedUrl, "_blank", "width=600,height=800");
});

copyLinkButton?.addEventListener("click", function () {
    const embedUrl = `${window.location}/embed-chat/${channelName}?session_id=${sessionId}`;
    navigator.clipboard.writeText(embedUrl).then(() => {
        // Change button text or add a class for visual feedback
        const originalText = copyLinkButton.textContent;
        copyLinkButton.textContent = "Copied!";
        copyLinkButton.disabled = true;

        setTimeout(() => {
            copyLinkButton.textContent = originalText;
            copyLinkButton.disabled = false;
        }, 2000);
    }).catch(err => {
        console.error('Error copying link:', err);
    });
});


// ===== INITIALIZATION =====
document.addEventListener('DOMContentLoaded', function() {
    setupEventListeners();
    initializeEventSource();
});