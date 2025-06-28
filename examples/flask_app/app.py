from flask import Flask, request, jsonify
import httpx
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

app = Flask(__name__)
GATEWAY_URL = "http://localhost:8080"

@app.route('/chat', methods=['POST'])
def chat():
    # Get JWT from request
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return {"error": "Authorization header required"}, 401
    
    # Forward to Attach Gateway
    try:
        response = httpx.post(
            f"{GATEWAY_URL}/api/chat",
            json=request.json,
            headers={"Authorization": auth_header},
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as e:
        return {"error": "Gateway unavailable"}, 503

if __name__ == '__main__':
    app.run(debug=True, port=5000) 