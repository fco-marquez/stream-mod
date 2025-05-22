from utils import cargar_modelo
from flask import Flask

app = Flask(__name__)
model = cargar_modelo()