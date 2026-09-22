import requests
import json
from bs4 import BeautifulSoup

url = "https://kingofshojo.cc/manga/vy5evrpl60cfvyzi/chapter-1/"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
r = requests.get(url, headers=headers)
soup = BeautifulSoup(r.text, "html.parser")
scripts = soup.find_all("script")
data = json.loads(scripts[4].string or scripts[4].text)

props = data["props"]
print("pages:", len(props.get("pages", [])))
print("pages sample:", props.get("pages")[:3])
print("paths:", props.get("paths"))
