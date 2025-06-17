const chatBox = document.getElementById('chat-box');
const modal = document.getElementById("message-modal");
const modalMsg = document.getElementById("modal-message");
const modalReason = document.getElementById("modal-reason");
const modalUser = document.getElementById("modal-user");
const modalTime = document.getElementById("modal-time");
const closeBtn = document.querySelector(".close-btn");
const moderateBtn = document.getElementById("moderate-btn");
const unmoderateBtn = document.getElementById("unmoderate-btn");
const reasonSelect = document.getElementById("moderation-reason");

const evtSource = new EventSource("/chat");
let chatMessages = []; // Store all messages
let lastMessageId = 0; // Track the last message we've processed
let currentMessage = null;  // Store the current message being viewed in modal

async function updateModerationReasons(reasons) {
    try {
        const response = await fetch('/update_reasons', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
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

// Update the event listeners in index.html to use this function
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
    
    // If message is moderated, only show it if its reason is selected
    // This means if the reason is disabled, the message will be shown as unmoderated
    return window.selectedReasons.has(data.reason);
}

function refreshChatDisplay() {
    // Clear chat box
    chatBox.innerHTML = '';
    
    // Re-add messages that should be shown
    chatMessages.forEach(data => {
        const msg = createMessageElement(data);
        // If the message was moderated but its reason is not selected,
        // show it as an unmoderated message
        if (data.moderated && !window.selectedReasons.has(data.reason)) {
            msg.classList.remove("moderated", "blurred");
            msg.innerHTML = `<strong>${data.timestamp} - ${data.username}:</strong> ${data.text}`;
            msg.style.cursor = "default";
            // Remove click handler for viewing moderated message
            msg.replaceWith(msg.cloneNode(true));
        }
        chatBox.appendChild(msg);
    });
    
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function toggleModeration(message, reason) {
    if (!reason && !message.moderated) {
        alert("Por favor seleccione una razón para moderar el mensaje");
        return;
    }

    try {
        const response = await fetch('/toggle_moderation', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                username: message.username,
                timestamp: message.timestamp,
                text: message.text,
                reason: reason || message.reason
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
                chatMessages[messageIndex].reason = reason || message.reason;
                
                // Update UI
                refreshChatDisplay();
                updateModalButtons(message);
                reasonSelect.value = '';  // Reset reason select
            }
        }
    } catch (error) {
        console.error('Error toggling moderation status:', error);
    }
}

function updateModalButtons(message) {
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

function createMessageElement(data) {
    const msg = document.createElement("p");
    
    if (data.moderated) {
        msg.classList.add("moderated");
    }

    if (data.moderated) {
        msg.classList.add("blurred");
        msg.innerHTML = `<strong>${data.timestamp} - ${data.username}:</strong> [${data.reason}] Click to view`;
        msg.style.cursor = "pointer";
        msg.addEventListener("click", () => {
            currentMessage = data;
            modalMsg.textContent = data.text;
            modalReason.textContent = data.reason;
            modalUser.textContent = data.username;
            modalTime.textContent = data.timestamp;
            updateModalButtons(data);
            modal.classList.remove("hidden");
        });
    } else {
        msg.innerHTML = `<strong>${data.timestamp} - ${data.username}:</strong> ${data.text}`;
        msg.addEventListener("click", () => {
            currentMessage = data;
            modalMsg.textContent = data.text;
            modalReason.textContent = "No moderado";
            modalUser.textContent = data.username;
            modalTime.textContent = data.timestamp;
            updateModalButtons(data);
            modal.classList.remove("hidden");
        });
    }
    
    return msg;
}

evtSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    // Check if we've already processed this message
    const messageId = `${data.username}-${data.timestamp}-${data.text}`;
    if (chatMessages.some(msg => 
        msg.username === data.username && 
        msg.timestamp === data.timestamp && 
        msg.text === data.text
    )) {
        return; // Skip if we've already seen this message
    }
    
    // Add to our message store
    chatMessages.push(data);
    
    // Only show if it matches our current filters
    if (shouldShowMessage(data)) {
        const msg = createMessageElement(data);
        chatBox.appendChild(msg);
        chatBox.scrollTop = chatBox.scrollHeight;
    }
};

// Add event listeners for moderation buttons
moderateBtn.addEventListener('click', () => {
    if (currentMessage) {
        toggleModeration(currentMessage, reasonSelect.value);
    }
});

unmoderateBtn.addEventListener('click', () => {
    if (currentMessage) {
        toggleModeration(currentMessage);
    }
});

// Reset modal when closed
closeBtn.onclick = function() {
    modal.classList.add("hidden");
    reasonSelect.value = '';
    currentMessage = null;
};

window.onclick = function(event) {
    if (event.target == modal) {
        modal.classList.add("hidden");
        reasonSelect.value = '';
        currentMessage = null;
    }
};
