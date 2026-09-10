from optimum.intel.openvino import OVModelForCausalLM
from transformers import AutoTokenizer, pipeline

# --- CONFIGURAÇÃO ---
# Usando o Repositório Oficial da OpenVINO (Garantido)
model_id = "OpenVINO/Phi-3-mini-4k-instruct-int4-ov"
DEVICE = "GPU" 

print(f"--- Carregando o modelo {model_id} na {DEVICE}... ---")
print("(Isso vai baixar aprox. 2.5GB. Aguarde...)")

# 1. Carregar Modelo e Tokenizer
try:
    model = OVModelForCausalLM.from_pretrained(model_id, device=DEVICE)
    tokenizer = AutoTokenizer.from_pretrained(model_id)
except Exception as e:
    print(f"Erro ao carregar modelo: {e}")
    exit()

# 2. Criar o Pipeline de Texto
pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)

# 3. O Prompt
prompt = "Explique para mim, de forma resumida, qual a vantagem de usar Linux para programação."

# Formatar para o estilo de chat do Phi-3
messages = [
    {"role": "user", "content": prompt},
]
formatted_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

# 4. Gerar a resposta
print(f"\n--- Gerando resposta para: '{prompt}' ---\n")
# max_new_tokens limita o tamanho da resposta para ser rápido
outputs = pipe(formatted_prompt, max_new_tokens=300, do_sample=True, temperature=0.7)

# Limpar a saída
print(outputs[0]["generated_text"].split("<|assistant|>")[-1].strip())
