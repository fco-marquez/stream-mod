// Get session ID from the template (make sure this is added to your HTML)
const sessionId = document.getElementById('session-id')?.value || '';

const chatBox = document.getElementById('chat-box');
const modal = document.getElementById("message-modal");
const modalMsg = document.getElementById("modal-message");
const modalReason = document.getElementById("modal-reason");
const modalUser = document.getElementById("modal-user");
const modalTime = document.getElementById("modal-time");
const closeBtn = document.querySelector(".close-btn");
const moderateBtn = document.getElementById("moderate-btn");
const unmoderateBtn = document.getElementById("unmoderate-btn");

// Get currently selected reasons from checkboxes
function getSelectedReasons() {
    const checkboxes = document.querySelectorAll('#moderation-reason input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// Clear all reason checkboxes
function clearReasonCheckboxes() {
    const checkboxes = document.querySelectorAll('#moderation-reason input[type="checkbox"]');
    checkboxes.forEach(cb => cb.checked = false);
}

// Initialize EventSource with session ID
const evtSource = new EventSource(window.location+`/chat?session_id=${sessionId}`);

let chatMessages = []; // Store all messages
let currentMessage = null;  // Store the current message being viewed in modal

// Initialize selectedReasons for filtering display
if (typeof window.selectedReasons === 'undefined') {
    window.selectedReasons = new Set([
        'Garabato',
        'Spam',
        'Racismo/Xenofobia',
        'Homofobia',
        'Contenido sexual',
        'Insulto',
        'Machismo/Misoginia/Sexismo',
        'Divulgación de información personal (doxxing)',
        'Otros',
        'Amenaza/acoso violento',
        'No baneable'
    ]);
}

async function updateModerationReasons(reasons) {
    try {
        const response = await fetch(window.location+'/update_reasons', {
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

// Update the selected reasons for filtering display
window.updateSelectedReasons = function(reason, isChecked) {
    if (isChecked) {
        window.selectedReasons.add(reason);
    } else {
        window.selectedReasons.delete(reason);
    }
    updateModerationReasons(window.selectedReasons);
    // Refresh display when reasons change
    refreshChatDisplay();
};

function shouldShowMessage(data) {
    // If message is not moderated, always show it
    if (!data.moderated) return true;
    
    // If message is moderated, check if any of its reasons are selected
    if (data.reasons && Array.isArray(data.reasons)) {
        return data.reasons.some(reason => window.selectedReasons.has(reason));
    }
    
    // Fallback for single reason (backward compatibility)
    if (data.reason) {
        return window.selectedReasons.has(data.reason);
    }
    
    return false;
}

function refreshChatDisplay() {
    // Clear chat box
    chatBox.innerHTML = '';
    
    // Re-add messages that should be shown
    chatMessages.forEach(data => {
        const msg = createMessageElement(data);
        chatBox.appendChild(msg);
    });
    
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function toggleModeration(message, reasons = null) {
    // If unmoderate (no reasons provided), proceed
    // If moderate, check that reasons are provided
    if (!message.moderated && (!reasons || reasons.length === 0)) {
        alert("Por favor seleccione una razón para moderar el mensaje");
        return;
    }

    try {
        const response = await fetch(window.location+'/toggle_moderation', {
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
            // Update the message in our store
            const messageIndex = chatMessages.findIndex(msg => 
                msg.username === message.username && 
                msg.timestamp === message.timestamp && 
                msg.text === message.text
            );
            
            if (messageIndex !== -1) {
                chatMessages[messageIndex].moderated = data.action === 'moderated';
                if (data.action === 'moderated' && reasons) {
                    chatMessages[messageIndex].reasons = reasons;
                    // Keep backward compatibility
                    chatMessages[messageIndex].reason = reasons[0];
                } else if (data.action === 'unmoderated') {
                    delete chatMessages[messageIndex].reasons;
                    delete chatMessages[messageIndex].reason;
                }
                
                // Update current message if it's the same
                if (currentMessage && 
                    currentMessage.username === message.username &&
                    currentMessage.timestamp === message.timestamp &&
                    currentMessage.text === message.text) {
                    currentMessage = chatMessages[messageIndex];
                }
                
                // Update UI
                refreshChatDisplay();
                updateModalButtons(chatMessages[messageIndex]);
                clearReasonCheckboxes();  // Clear checkboxes after action
            }
        }
    } catch (error) {
        console.error('Error toggling moderation status:', error);
    }
}

function updateModalButtons(message) {
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

function getDisplayReason(data) {
    if (data.reasons && Array.isArray(data.reasons) && data.reasons.length > 0) {
        return data.reasons.join(', ');
    }
    return data.reason || 'Moderado';
}

function createMessageElement(data) {
    const msg = document.createElement("p");
    
    // Determine if message should be shown as moderated based on current filters
    const isModeratedAndVisible = data.moderated && shouldShowMessage(data);
    
    if (isModeratedAndVisible) {
        msg.classList.add("moderated", "blurred");
        const displayReason = getDisplayReason(data);
        msg.innerHTML = `<strong>${data.timestamp} - ${data.username}:</strong> [${displayReason}] Click to view`;
        msg.style.cursor = "pointer";
    } else {
        // Show as unmoderated (either truly unmoderated or moderated but filtered out)
        msg.innerHTML = `<strong>${data.timestamp} - ${data.username}:</strong> ${data.text}`;
        msg.style.cursor = "pointer";
    }
    
    // Add click event for modal
    msg.addEventListener("click", () => {
        currentMessage = data;
        modalMsg.textContent = data.text;
        modalReason.textContent = data.moderated ? getDisplayReason(data) : "No moderado";
        modalUser.textContent = data.username;
        modalTime.textContent = data.timestamp;
        updateModalButtons(data);
        modal.classList.remove("hidden");
    });
    
    return msg;
}

evtSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    // Check if we've already processed this message
    if (chatMessages.some(msg => 
        msg.username === data.username && 
        msg.timestamp === data.timestamp && 
        msg.text === data.text
    )) {
        return; // Skip if we've already seen this message
    }
    
    // Add to our message store
    chatMessages.push(data);
    
    // Create and add the message element
    const msg = createMessageElement(data);
    chatBox.appendChild(msg);
    chatBox.scrollTop = chatBox.scrollHeight;
};

// Handle EventSource errors
evtSource.onerror = function(event) {
    console.error('EventSource failed:', event);
    // You might want to implement reconnection logic here
};

// Add event listeners for moderation buttons
if (moderateBtn) {
    moderateBtn.addEventListener('click', () => {
        if (currentMessage) {
            const selectedReasons = getSelectedReasons();
            if (selectedReasons.length > 0) {
                toggleModeration(currentMessage, selectedReasons);
                modal.classList.add("hidden");
                clearReasonCheckboxes(); // Clear selected reasons
                currentMessage = null;
            } else {
                alert("Por favor seleccione una razón para moderar el mensaje");
            }
        }
    });
}

if (unmoderateBtn) {
    unmoderateBtn.addEventListener('click', () => {
        if (currentMessage) {
            toggleModeration(currentMessage);
        }
    });
}

// Reset modal when closed
if (closeBtn) {
    closeBtn.onclick = function() {
        modal.classList.add("hidden");
        clearReasonCheckboxes(); // Clear selected reasons
        currentMessage = null;
    };
}

window.onclick = function(event) {
    if (event.target == modal) {
        modal.classList.add("hidden");
        clearReasonCheckboxes();
        currentMessage = null;
    }
};

// Clean up EventSource when page unloads
window.addEventListener('beforeunload', function() {
    if (evtSource) {
        evtSource.close();
    }
});

// Initialize checkbox event listeners when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners to all moderation reason checkboxes
    const checkboxes = document.querySelectorAll('#moderation-reason input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            // This is for display filtering, not for moderation action
            // The moderation action uses getSelectedReasons() when the moderate button is clicked
            console.log('Checkbox changed:', this.value, this.checked);
        });
    });
});