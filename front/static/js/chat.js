
const chatBox = document.getElementById('chat-box');
const modal = document.getElementById("message-modal");
const modalMsg = document.getElementById("modal-message");
const modalReason = document.getElementById("modal-reason");
const closeBtn = document.querySelector(".close-btn");

const evtSource = new EventSource("/chat");

evtSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    const msg = document.createElement("p");

    if (data.moderated) {
        msg.classList.add("blurred");
        msg.innerHTML = `<strong>${data.timestamp} - ${data.username}:</strong> [Flagged] Click to view`;
        msg.style.cursor = "pointer";
        msg.addEventListener("click", () => {
            modalMsg.textContent = data.text;
            modalReason.textContent = data.reason;
            document.getElementById("modal-user").textContent = data.username;
            document.getElementById("modal-time").textContent = data.timestamp;
            modal.classList.remove("hidden");
        });
    } else {
        msg.innerHTML = `<strong>${data.timestamp} - ${data.username}:</strong> ${data.text}`;
    }

    chatBox.appendChild(msg);
    chatBox.scrollTop = chatBox.scrollHeight;
};

closeBtn.onclick = function() {
    modal.classList.add("hidden");
};

window.onclick = function(event) {
    if (event.target == modal) {
        modal.classList.add("hidden");
    }
};
