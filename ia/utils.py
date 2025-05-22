import pickle
import re
from transformers import AutoTokenizer, AutoModelForSequenceClassification, AutoModel
import torch
import numpy as np
from torch import nn

# Define moderation categories and their labels
MODERATION_CATEGORIES = {
    0: "appropriate",  # No moderation needed
    1: "hate_speech",  # Hate speech or discriminatory content
    2: "harassment",   # Harassment or bullying
    3: "inappropriate", # Inappropriate content
    4: "spam",        # Spam or self-promotion
}

class ModerationClassifier(nn.Module):
    def __init__(self, base_model, num_labels):
        super().__init__()
        self.bert = base_model
        self.classifier = nn.Linear(base_model.config.hidden_size, num_labels)
        
    def forward(self, **inputs):
        outputs = self.bert(**inputs)
        # Get the [CLS] token representation (first token of the sequence)
        cls_output = outputs.last_hidden_state[:, 0, :]  # Shape: [batch_size, hidden_size]
        # Pass through classifier
        logits = self.classifier(cls_output)  # Shape: [batch_size, num_labels]
        return logits

def cargar_modelo(model_name="dccuchile/tulio-chilean-spanish-bert"):
    """
    Load the Tulio BERT model and tokenizer for moderation
    """
    # Load base model and tokenizer
    base_model = AutoModel.from_pretrained(model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    
    # Create classification head
    model = ModerationClassifier(base_model, num_labels=len(MODERATION_CATEGORIES))
    
    # Note: In a production environment, you would load fine-tuned weights here
    # model.load_state_dict(torch.load('path_to_fine_tuned_weights.pt'))
    
    return model, tokenizer

def get_prediction(text, model, tokenizer, threshold=0.3):
    """
    Get moderation prediction and reason for a message
    
    Parameters:
    text (str): Message to moderate
    model: The loaded BERT model with classification head
    tokenizer: The loaded tokenizer
    threshold (float): Confidence threshold for moderation
    
    Returns:
    tuple: (approved: bool, reason: str)
    """
    # Prepare the input
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding=True,
        add_special_tokens=True
    )
    
    # Get model prediction
    model.eval()  # Set to evaluation mode
    with torch.no_grad():
        try:
            logits = model(**inputs)  # Shape: [1, num_labels]
            probabilities = torch.softmax(logits, dim=1)
            prediction = torch.argmax(probabilities, dim=1).item()
            confidence = probabilities[0][prediction].item()
            
            # If confidence is below threshold, consider it appropriate
            if confidence < threshold:
                return True, "appropriate"
            
            # Get the reason from our categories
            reason = MODERATION_CATEGORIES[prediction]
            
            # Message is approved only if it's categorized as appropriate
            approved = reason == "appropriate"
            
            return approved, reason
            
        except Exception as e:
            print(f"Error in prediction: {str(e)}")
            return True, "appropriate"  # Default to approved on error

def moderate_message(text, model, tokenizer):
    """
    Wrapper function to moderate a message using the BERT model
    
    Parameters:
    text (str): Message to moderate
    model: The loaded BERT model
    tokenizer: The loaded tokenizer
    
    Returns:
    tuple: (approved: bool, reason: str)
    """
    try:
        return get_prediction(text, model, tokenizer)
    except Exception as e:
        print(f"Error in moderation: {str(e)}")
        # In case of error, approve the message to avoid blocking legitimate content
        return True, "appropriate"

# Función de preprocesamiento del mensaje (no se si es)
def preprocesar_mensaje(mensaje):
    mensaje = mensaje.lower()
    mensaje = re.sub(r'[^\w\s]', '', mensaje)  # eliminar puntuación
    return mensaje
