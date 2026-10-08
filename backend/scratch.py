import requests
res = requests.post("http://localhost:8000/api/sessions", json={"repo_url": "https://github.com/fastapi/fastapi"})
print(res.status_code, res.text)
