from transformers import AutoTokenizer, AutoModelForSequenceClassification, AutoModel, BertForSequenceClassification
import torch
import numpy as np
from torch import nn
import os, shutil, hashlib, re, json

# Define moderation categories and their labels (updated to match fine-tuned model)
MODERATION_CATEGORIES = {
    0: 'Garabato',
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
    """
    Download all model files from a public Google Drive folder and validate them.

    Relies on the environment variable MODEL_FOLDER_ID and uses gdown to download the entire folder.
    Validates JSON and safetensors files. Skips re-downloading valid files.
    """
    from safetensors.torch import load_file  # For safetensors validation

    folder_id = os.getenv("MODEL_FOLDER_ID")
    if not folder_id:
        raise ValueError("MODEL_FOLDER_ID environment variable is not set.")

    url = f"https://drive.google.com/drive/folders/{folder_id}"
    os.makedirs(model_dir, exist_ok=True)

    print(f"Downloading model files from folder: {url}")
    
    # Use a temporary directory to avoid overwriting valid files
    temp_dir = os.path.join(model_dir, "__temp_download")
    os.makedirs(temp_dir, exist_ok=True)

    # Download all files in the folder
    gdown.download_folder(url=url, output=temp_dir, quiet=False, use_cookies=False)

    # Validate and move each file individually
    for filename in os.listdir(temp_dir):
        temp_file_path = os.path.join(temp_dir, filename)
        target_file_path = os.path.join(model_dir, filename)

        # If already exists and valid, skip
        if os.path.exists(target_file_path):
            try:
                if filename.endswith('.safetensors'):
                    load_file(target_file_path)
                elif filename.endswith('.json'):
                    with open(target_file_path, 'r', encoding='utf-8') as f:
                        json.load(f)
                print(f"{filename} exists and is valid, skipping download")
                continue
            except Exception as e:
                print(f"{filename} exists but is corrupted, will replace: {str(e)}")
                os.remove(target_file_path)

        # Validate the downloaded file
        try:
            if filename.endswith('.safetensors'):
                load_file(temp_file_path)
            elif filename.endswith('.json'):
                with open(temp_file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
            
            # Move the file if valid
            shutil.move(temp_file_path, target_file_path)
            print(f"Successfully downloaded and verified {filename}")
        except Exception as e:
            print(f"Downloaded {filename} is corrupted: {str(e)}")
            os.remove(temp_file_path)

    # Cleanup temp directory
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
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

import torch

# Example threshold
THRESHOLD = 0.5

def get_prediction(text, model, tokenizer):
    """
    Get moderation prediction and reasons for a message (multi-label)

    Parameters:
    text (str): Message to moderate
    model: The loaded multi-label classification model
    tokenizer: The loaded tokenizer

    Returns:
    tuple: (approved: bool, reasons: List[str])
    """
    # Prepare the input
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=128,
        padding=True,
        add_special_tokens=True
    )
    
    model.eval()
    with torch.no_grad():
        try:
            outputs = model(**inputs)
            logits = outputs.logits
            probabilities = torch.sigmoid(logits).squeeze()  # For multi-label, apply sigmoid
            
            # Get predicted categories (multi-label)
            predicted_indices = (probabilities >= THRESHOLD).nonzero(as_tuple=True)[0].tolist()
            reasons = [MODERATION_CATEGORIES[i] for i in predicted_indices]

            # If all categories are non-baneable, approve
            approved = all(reason == 'No baneable' for reason in reasons) if reasons else True

            return approved, reasons if reasons else ["No baneable"]

        except Exception as e:
            print(f"Error in prediction: {str(e)}")
            return True, ["appropriate"]  # Fallback


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
