# AIrewrite

AIrewrite is an automated content rewriting and management tool powered by various AI models (Gemini, ChatGPT, etc.).

## Prerequisites

- Python 3.10 or higher
- macOS (for building the DMG installer)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/aiautotool/airewrite.git
   cd airewrite
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

The application requires API keys and OAuth credentials to function correctly.

1. **Create the Config File**:
   Copy the example configuration file:
   ```bash
   cp config.example.json config.json
   ```

2. **Edit `config.json`**:
   Open `config.json` and fill in your credentials:
   ```json
   {
       "google_client_id": "YOUR_GOOGLE_CLIENT_ID",
       "google_client_secret": "YOUR_GOOGLE_CLIENT_SECRET",
       "gemini_api_keys": [
           "YOUR_GEMINI_API_KEY_1",
           "YOUR_GEMINI_API_KEY_2"
       ]
   }
   ```
   *   **google_client_id / secret**: OAuth 2.0 credentials from Google Cloud Console (for Blogger/Drive integration).
   *   **gemini_api_keys**: List of API keys for Google Gemini models.

## Running in Development

To run the application directly from source:

```bash
python3 rewrite_app.py
```

## Building the Application (macOS)

To build a standalone `.app` and a `.dmg` installer:

1. Ensure build tools are installed:
   ```bash
   pip install pyinstaller
   # You may need to install create-dmg via brew if not available
   # brew install create-dmg
   ```

2. Run the rebuild script:
   ```bash
   chmod +x rebuild.sh
   ./rebuild.sh
   ```

3. **Output**:
   - The compiled application will be in `dist/AIrewrite.app`.
   - The DMG installer will be created in the current directory (e.g., `AIrewrite 1.1.2.dmg`).

## Project Structure

- `rewrite_app.py`: Main entry point and UI logic.
- `ai_agent.py`: Handles interactions with AI models.
- `account_manager.py`: Manages Google accounts and tokens.
- `sheet_manager.py`: Integration with Google Sheets.
- `crawler/`: Scrapy project for advanced crawling.
- `antigravity_proxy/`: Proxy and account session storage.

## License

Internal Tool - All Rights Reserved.
