from utils import cargar_modelo
from flask import Flask
from dotenv import load_dotenv
import os

# Load .env from parent directory
load_dotenv('.env')

app = Flask(__name__)
model, tokenizer = cargar_modelo()  # Load both model and tokenizer
