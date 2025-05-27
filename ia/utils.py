import re
from transformers import AutoTokenizer, AutoModelForSequenceClassification, AutoModel, BertForSequenceClassification
import torch
import numpy as np
from torch import nn
import os
import shutil
import hashlib

# Define moderation categories and their labels (updated to match fine-tuned model)
MODERATION_CATEGORIES = {
    0: 'Garabatos no peyorativos',
    1: 'Spam',
    2: 'Racismo/Xenofobia',
    3: 'Homofobia',
    4: 'Contenido sexual',
    5: 'Insulto',
    6: 'Machismo/Misoginia/Sexismo',
    7: 'Divulgación de información personal (doxxing)',
    8: 'Otros',
    9: 'Amenaza/acoso violento',
    10: 'No baneable'
}

class WeightedLossModel(BertForSequenceClassification):
    def _init_(self, config, class_weights=None):
        super()._init_(config)
        self.class_weights = class_weights
        
    def compute_loss(self, model_output, labels):
        logits = model_output.logits
        loss_fct = torch.nn.CrossEntropyLoss(weight=self.class_weights)
        return loss_fct(logits,labels)

def get_file_hash(filepath):
    """Calculate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

import gdown

def gdown_download(file_id, destination):
    url = f"https://drive.google.com/uc?id={file_id}"
    try:
        gdown.download(url, destination, quiet=False)
        return True
    except Exception as e:
        print(f"Error downloading {destination} with gdown: {str(e)}")
        return False

  
def drive_url(file_id):
    return f"https://drive.google.com/uc?export=download&id={file_id}"

def download_model_files(model_dir):
    """Download model files from Google Drive to the specified directory"""
    # Google Drive direct download links (replace with your actual file IDs)
    model_files = {
        'config.json': drive_url(os.getenv('CONFIG_JSON_ID')),
        'model.safetensors': drive_url(os.getenv('MODEL_SAFETENSORS_ID')),
        'tokenizer.json': drive_url(os.getenv('TOKENIZER_JSON_ID')),
        'tokenizer_config.json': drive_url(os.getenv('TOKENIZER_CONFIG_JSON_ID')),
        'special_tokens_map.json': drive_url(os.getenv('SPECIAL_TOKENS_MAP_ID')),
        'vocab.txt': drive_url(os.getenv('VOCAB_TXT_ID'))
    }

    # Create model directory if it doesn't exist
    os.makedirs(model_dir, exist_ok=True)
    
    # Download each file
    for filename, url in model_files.items():
        file_path = os.path.join(model_dir, filename)
        temp_path = file_path + '.tmp'
        
        # Skip if file exists and is valid
        if os.path.exists(file_path):
            try:
                # Try to validate the file based on its type
                if filename.endswith('.safetensors'):
                    from safetensors.torch import load_file
                    load_file(file_path)  # This will raise an error if file is corrupted
                elif filename.endswith('.json'):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        import json
                        json.load(f)  # This will raise an error if file is corrupted
                print(f"{filename} exists and is valid, skipping download")
                continue
            except Exception as e:
                print(f"{filename} exists but is corrupted, will redownload: {str(e)}")
                os.remove(file_path)
        
        print(f"Downloading {filename}...")
        file_id = url.split("id=")[-1]
        if gdown_download(file_id, temp_path):
            # Verify the downloaded file
            try:
                if filename.endswith('.safetensors'):
                    from safetensors.torch import load_file
                    load_file(temp_path)  # This will raise an error if file is corrupted
                elif filename.endswith('.json'):
                    with open(temp_path, 'r', encoding='utf-8') as f:
                        import json
                        json.load(f)  # This will raise an error if file is corrupted
                
                # If we get here, the file is valid, so move it to the final location
                shutil.move(temp_path, file_path)
                print(f"Successfully downloaded and verified {filename}")
            except Exception as e:
                print(f"Downloaded {filename} is corrupted: {str(e)}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise
        else:
            raise Exception(f"Failed to download {filename}")

def cargar_modelo(model_dir="modelo_final_guardado"):
    """
    Load the fine-tuned Tulio BERT model and tokenizer for moderation
    
    Parameters:
    model_dir (str): Directory where model files are/will be stored
    model_name (str): Name of the base model to use
    """
    try:
        # Download model files if they don't exist or are corrupted
        if not os.path.exists(model_dir) or not os.listdir(model_dir):
            print(f"Model files not found in {model_dir}, downloading...")
            download_model_files(model_dir)
        
        # Load base model and tokenizer
        print("Loading base model and tokenizer...")
        base_model = AutoModel.from_pretrained(model_dir)
        tokenizer = AutoTokenizer.from_pretrained(model_dir)
        
        # Create classification head with 11 classes
        print("Creating classification head...")
        model = WeightedLossModel.from_pretrained(model_dir)
        
        # Load fine-tuned weights
        print(f"Loading fine-tuned weights from {model_dir}...")
        model_file = os.path.join(model_dir, 'model.safetensors')
        if not os.path.exists(model_file):
            raise FileNotFoundError(f"No model.safetensors file found in {model_dir}")
        
        try:
            from safetensors.torch import load_file
            state_dict = load_file(model_file)
            # Handle both WeightedLossModel and BertForSequenceClassification state dicts
            if 'bert' in state_dict:
                model.load_state_dict(state_dict)
            else:
                # If it's a BertForSequenceClassification state dict, we need to adapt it
                adapted_state_dict = {}
                for k, v in state_dict.items():
                    if k.startswith('bert.'):
                        adapted_state_dict[k] = v
                    elif k.startswith('classifier.'):
                        adapted_state_dict[k] = v
                model.load_state_dict(adapted_state_dict, strict=False)
            print(f"Successfully loaded weights from {model_file}")
        except Exception as e:
            print(f"Error loading model weights: {str(e)}")
            print("Attempting to redownload model files...")
            download_model_files(model_dir)  # Try downloading again
            raise
        
        # Set model to evaluation mode
        model.eval()
        return model, tokenizer
        
    except Exception as e:
        print(f"Error loading model: {str(e)}")
        raise

def get_prediction(text, model, tokenizer):
    """
    Get moderation prediction and reason for a message
    
    Parameters:
    text (str): Message to moderate
    model: The loaded BERT model with classification head
    tokenizer: The loaded tokenizer
    
    Returns:
    tuple: (approved: bool, reason: str)
    """
    # Prepare the input
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=128,  # Updated to match training
        padding=True,
        add_special_tokens=True
    )
    
    # Get model prediction
    model.eval()  # Set to evaluation mode
    with torch.no_grad():
        try:
            outputs = model(**inputs)  # Get model outputs
            logits = outputs.logits  # Extract logits from outputs
            probabilities = torch.softmax(logits, dim=1)  # Apply softmax to logits
            prediction = torch.argmax(probabilities, dim=1).item()  # Get prediction from probabilities
            
            # Get the reason from our categories
            reason = MODERATION_CATEGORIES[prediction]
            
            approved = reason == 'No baneable'
            
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
    threshold (float): Confidence threshold for moderation
    
    Returns:
    tuple: (approved: bool, reason: str)
    """
    try:
        # Preprocess the message
        text = preprocesar_mensaje(text)
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
