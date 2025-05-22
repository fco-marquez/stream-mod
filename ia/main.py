# -*- coding: utf-8 -*- 
from app import app
from utils import get_prediction
from flask import Flask, jsonify, request

@app.route('ruta/proyecto', methods=['POST'])

def moderate():
    """
    Función para filtrar mensajes inapropiados de un chat en vivo.
    """
    # Obtener el mensaje del cuerpo de la solicitud
    data = request.get_json()
    mensaje = data['mensaje'] # Eventualmente incluir el tipo de usuario para filtro por reglas
    
    # Realizar la predicción
    prediction = get_prediction(mensaje)
    
    # Crear la respuesta JSON
    json_respuesta = {"prediction": prediction}
    
    # Imprimir la respuesta en la consola
    print("responder: {}".format(json_respuesta))
    
    # Devolver la respuesta JSON
    return jsonify(json_respuesta)

if __name__ == "__main__":
    app.run(port=7002)