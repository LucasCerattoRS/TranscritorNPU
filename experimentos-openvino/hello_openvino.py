import cv2
import numpy as np
import openvino as ov

# --- CONFIGURAÇÃO ---
MODEL_PATH = "resnet50.xml"
LABEL_PATH = "imagenet_2012.txt"
DEVICE = "GPU"

# Carregar as classes
with open(LABEL_PATH, "r") as f:
    classes = [line.strip() for line in f.readlines()]

# Inicializar OpenVINO
core = ov.Core()
model = core.read_model(model=MODEL_PATH)
compiled_model = core.compile_model(model=model, device_name=DEVICE)
output_layer = compiled_model.output(0)

# Preparar a imagem
image_filename = "imagem_teste.jpg"
image = cv2.imread(image_filename)

if image is None:
    print(f"Erro: Não encontrei '{image_filename}'.")
    exit()

# Redimensionar para 224x224 (padrão do modelo)
resized_image = cv2.resize(image, (224, 224))
input_image = np.expand_dims(resized_image.transpose(2, 0, 1), 0)

# Inferência
result = compiled_model([input_image])[output_layer]

# Resultado
result_index = np.argmax(result)
print(f"--- RESULTADO ---")
print(f"Dispositivo usado: {DEVICE}")
print(f"O modelo acha que isso é um(a): {classes[result_index]}")
