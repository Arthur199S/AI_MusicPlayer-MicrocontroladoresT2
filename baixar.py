import urllib.request
import zipfile
import os

print("Iniciando download do modelo de voz (45MB)...")
os.makedirs("models", exist_ok=True)

# Link dividido em partes para evitar que o seu terminal corte o texto
parte1 = "https://alphacephei.com"
parte2 = "vosk/models/vosk-model-small-pt-0.3.zip"
url_completa = parte1 + parte2

urllib.request.urlretrieve(url_completa, "models/model.zip")
print("Download concluído! Extraindo os arquivos...")

with zipfile.ZipFile("models/model.zip", "r") as zip_ref:
    zip_ref.extractall("models/")

os.remove("models/model.zip")
print("Concluído com sucesso! Pasta 'models/vosk-model-small-pt-0.3' criada.")
