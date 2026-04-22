import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_KEY = os.getenv("TEXTBEE_API_KEY")
DEVICE_ID = os.getenv("TEXTBEE_DEVICE_ID")

def send_sms(to_number, message_text):
    url = f"https://api.textbee.dev/api/v1/gateway/devices/{DEVICE_ID}/send-sms"
    
    payload = {
        "recipients": [to_number], 
        "message": message_text
    }
    
    headers = {
        "x-api-key": API_KEY
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200 or response.status_code == 201:
            return "Success! Message sent successfully."
        else:
            return f": {response.status_code} - {response.text}"
    except Exception as e:
        return f"Exception: {str(e)}"

result = send_sms("+919537150942", "send")
print(result)

