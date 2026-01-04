from flask import Flask, request, jsonify
from ai_agent import AIAgent
import os

app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "online",
        "message": "AI Agent Web API is running",
        "supported_models": ["gemini", "custom-gemini", "pollinations", "mimo", "llm7"],
        "endpoints": {
            "/api/generate": "POST - {prompt, system_prompt, model, temperature, max_tokens}"
        }
    })

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.get_json() or {}
    
    # Fallback to form data if JSON is empty
    if not data:
        data = request.form.to_dict()

    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"error": "Missing 'prompt' parameter"}), 400

    system_prompt = data.get('system_prompt')
    model = data.get('model')
    temperature = float(data.get('temperature', 0.7))
    max_tokens = int(data.get('max_tokens', 8000))

    try:
        result = AIAgent.call_ai_agent(
            prompt=prompt, 
            system_prompt=system_prompt, 
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        if result:
            return jsonify({
                "success": True,
                "result": result
            })
        else:
            return jsonify({
                "success": False,
                "error": "AI failed to generate a response"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    # Get port from environment or use 5005
    port = int(os.environ.get('PORT', 5005))
    print(f"Starting AI API Server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)
