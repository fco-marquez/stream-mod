from utils import cargar_modelo
from flask import Flask

app = Flask(__name__)
model, tokenizer = cargar_modelo()  # Load both model and tokenizer
