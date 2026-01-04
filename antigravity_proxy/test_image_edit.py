
import requests
import json
import base64
import os

# Helper to read image as base64
def get_base64_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def test_image_edit():
    url = "http://localhost:5007/v1/chat/completions" # Using the OpenAI-compatible endpoint we've been using
    
    # We'll use the gemini-3-pro-image model
    # Note: Our proxy maps gemini-3-pro-image to the image_gen requestType
    
    image_path = "test_image.jpg"
    if not os.path.exists(image_path):
        print(f"Error: {image_path} not found. Run test_image_gen.py first.")
        return

    b64_data = get_base64_image(image_path)
    
    # In OpenAI format, we usually send image_url
    payload = {
        "model": "gemini-3-pro-image",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Make the apple in this image blue."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_data}"
                        }
                    }
                ]
            }
        ]
    }

    print("--- Testing Image Editing (via OpenAI Endpoint) ---")
    resp = requests.post(url, json=payload, timeout=120)
    
    if resp.ok:
        print("✅ Success!")
        data = resp.json()
        content = data['choices'][0]['message']['content']
        print(f"Content length: {len(content)}")
        
        if "![" in content and "data:image" in content:
            print("Image detected in markdown!")
            # Extract base64
            parts = content.split("base64,")
            if len(parts) > 1:
                img_b64 = parts[1].split(")")[0]
                with open("test_image_edited.jpg", "wb") as f:
                    f.write(base64.b64decode(img_b64))
                print("Saved to test_image_edited.jpg")
        else:
            print("No image found in response content.")
            print("Response:", content)
    else:
        print(f"❌ Failed: {resp.status_code}")
        print(resp.text)

if __name__ == "__main__":
    test_image_edit()
