import pickle
import re
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from app import model
# Cargar el modelo desde disco
def cargar_modelo(ruta_modelo="modelo_tulio_moderacion.pkl"):
    with open(ruta_modelo, "rb") as f:
        modelo = pickle.load(f)
    return modelo

# Función de preprocesamiento del mensaje (no se si es)
def preprocesar_mensaje(mensaje):
    mensaje = mensaje.lower()
    mensaje = re.sub(r'[^\w\s]', '', mensaje)  # eliminar puntuación
    return mensaje

def get_prediction(msj):
    """
    Función para predecir la clase de un mensaje para determinar si debe ser baneado
    
    Parameters:
    msj (str): Mensaje a predecir
    """
    print("evaluando mensaje en la red...")
    # Preprocesar el mensaje (definir la función de preprocesamiento)
    # msj = preprocesar_mensaje(msj)
    msj_pre = msj.strip()
    prediction = model.predict([msj_pre])[0]
    return prediction
