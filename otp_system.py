import os
import requests
import random
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TEXTBEE_API_KEY")
DEVICE_ID = os.getenv("TEXTBEE_DEVICE_ID")

def start_otp_process(phone_number):
    generated_otp = random.randint(10000, 99999)
    
    url = f"https://api.textbee.dev/api/v1/gateway/devices/{DEVICE_ID}/send-sms"
    
    payload = {
        "recipients": [phone_number],
        "message": f"Your Verification OTP is: {generated_otp}. Do not share it."
    }
    headers = {"x-api-key": API_KEY}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code in [200, 201]:
            print(f"Success: OTP sent to {phone_number}")
            
            user_input = input("Enter the 4-digit OTP you received: ")
            
            if user_input == str(generated_otp):
                print("---------------------------------")
                print("VERIFICATION SUCCESSFUL!")
                print("Welcome, you can now use the app.")
                print("---------------------------------")
            else:
                print("Invalid OTP! Access Denied.")
        else:
            print(f"Error sending SMS: {response.status_code}")
            
    except Exception as e:
        print(f"Connection Error: {str(e)}")

target = "+919537150942"
start_otp_process(target)

