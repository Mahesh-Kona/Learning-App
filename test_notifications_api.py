import requests

def test_get_notifications():
    url = "http://127.0.0.1:5000/api/notifications"
    # If authentication is required, add headers or cookies here
    response = requests.get(url)
    print("Status Code:", response.status_code)
    print("Response JSON:", response.json())

if __name__ == "__main__":
    test_get_notifications()
