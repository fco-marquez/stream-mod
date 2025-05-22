const chatBox = document.getElementById('chat-box');
const modal = document.getElementById("message-modal");
const modalMsg = document.getElementById("modal-message");
const modalReason = document.getElementById("modal-reason");
const modalUser = document.getElementById("modal-user");
const modalTime = document.getElementById("modal-time");
const closeBtn = document.querySelector(".close-btn");

const evtSource = new EventSource("/chat");
let chatMessages = []; // Store all messages
let lastMessageId = 0; // Track the last message we've processed

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
    if (!data.moderated) return true;
    return window.selectedReasons.has(data.reason);
}

function refreshChatDisplay() {
    // Clear chat box
    chatBox.innerHTML = '';
    
    // Re-add messages that should be shown
    chatMessages.forEach(data => {
        if (shouldShowMessage(data)) {
            const msg = createMessageElement(data);
            chatBox.appendChild(msg);
        }
    });
    
    chatBox.scrollTop = chatBox.scrollHeight;
}

function createMessageElement(data) {
    const msg = document.createElement("p");

    if (data.moderated) {
        msg.classList.add("blurred");
        msg.innerHTML = `<strong>${data.timestamp} - ${data.username}:</strong> [${data.reason}] Click to view`;
        msg.style.cursor = "pointer";
        msg.addEventListener("click", () => {
            modalMsg.textContent = data.text;
            modalReason.textContent = data.reason;
            modalUser.textContent = data.username;
            modalTime.textContent = data.timestamp;
            modal.classList.remove("hidden");
        });
    } else {
        msg.innerHTML = `<strong>${data.timestamp} - ${data.username}:</strong> ${data.text}`;
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

closeBtn.onclick = function() {
    modal.classList.add("hidden");
};

window.onclick = function(event) {
    if (event.target == modal) {
        modal.classList.add("hidden");
    }
};
