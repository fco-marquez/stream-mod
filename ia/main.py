from app import app, model, tokenizer
from utils import moderate_message
from flask import Flask, jsonify, request

@app.route('/moderate', methods=['POST'])
def moderate():
    """
    Endpoint to moderate messages using a multi-label BERT model.
    Returns moderation status and list of reasons.
    """
    try:
        # Get the message from request
        data = request.get_json()
        if not data or 'mensaje' not in data:
            return jsonify({
                "error": "No message provided",
                "status": "error"
            }), 400

        message = data['mensaje']
        
        # Get moderation result
        approved, reasons = moderate_message(message, model, tokenizer)
        
        # Create response
        response = {
            "status": "success",
            "approved": approved,
            "reasons": reasons,
            "message": message
        }
        
        print(f"Moderation result: {response}")
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in moderation endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    app.run(port=7012, debug=True)
