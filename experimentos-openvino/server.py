import sys

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from optimum.intel.openvino import OVModelForCausalLM
from transformers import AutoTokenizer, pipeline

# --- CONFIGURAÇÃO ---
# Se a GPU continuar dando erro, mantemos CPU que é estável no Core Ultra
DEVICE = "GPU" 
MODEL_ID = "OpenVINO/Phi-3-mini-4k-instruct-int4-ov"

app = FastAPI(title="OpenVINO LLM Server")

print(f"--- Carregando Modelo {MODEL_ID} na {DEVICE}... ---")
try:
    model = OVModelForCausalLM.from_pretrained(MODEL_ID, device=DEVICE)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)
    print("--- Modelo Carregado com Sucesso! ---")
except Exception as e:
    print(f"ERRO CRÍTICO: {e}", file=sys.stderr)
    sys.exit(1)

# Modelos de dados para imitar a API da OpenAI (básico)
class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = "local-model"
    messages: List[Message]
    max_tokens: Optional[int] = 500
    temperature: Optional[float] = 0.7

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # 1. Formatar o prompt
    # Converter o formato de chat (mensagens) para o texto único que o modelo entende
    chat_input = [msg.dict() for msg in request.messages]
    formatted_prompt = tokenizer.apply_chat_template(chat_input, tokenize=False, add_generation_prompt=True)
    
    # 2. Gerar resposta
    outputs = pipe(
        formatted_prompt, 
        max_new_tokens=request.max_tokens, 
        do_sample=True, 
        temperature=request.temperature
    )
    
    generated_text = outputs[0]["generated_text"].split("<|assistant|>")[-1].strip()

    # 3. Retornar no formato JSON que ferramentas de IA esperam
    return {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "created": 1677652288,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": generated_text
            },
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }

if __name__ == "__main__":
    # Roda o servidor na porta 8000, só nesta máquina (o llm-council chama em localhost).
    # Expor na rede é escolha explícita: HOST=0.0.0.0 python server.py
    import os
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
