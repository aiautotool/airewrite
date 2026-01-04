
import requests
import json
import base64
import os

PROXY_URL = "http://localhost:5007/v1/chat/completions"

def test_image_generation():
    payload = {
        "model": "gemini-3-pro-image",
        "messages": [
            {"role": "user", "content": "Generate an image of a red apple on a wooden table"}
        ]
    }
    
    print("\n--- Testing Image Generation (OpenAI Endpoint) ---")
    try:
        resp = requests.post(PROXY_URL, json=payload, timeout=60)
        
        if resp.status_code == 200:
            print("✅ Success!")
            data = resp.json()
            content = data['choices'][0]['message']['content']
            print(f"Content length: {len(content)}")
            if "![Generated Image](data:" in content:
                print("Image detected in markdown!")
                # Extract and save
                start = content.find("base64,") + 7
                end = content.find(")")
                b64_data = content[start:end]
                
                with open("test_image.jpg", "wb") as f:
                    f.write(base64.b64decode(b64_data))
                print("Saved to test_image.jpg")
            else:
                print("Response content:", content[:200])
        else:
            print(f"❌ Failed: {resp.status_code}")
            print(resp.text)
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_image_generation()
