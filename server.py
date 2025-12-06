import os
import tempfile
import wave
import struct
from fastapi import FastAPI, WebSocket
from groq import Groq

# --- НАСТРОЙКИ ---
PORT = int(os.environ.get("PORT", 8080))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

app = FastAPI()
groq_client = Groq(api_key=GROQ_API_KEY)

def get_groq_response(text):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты голосовой ассистент. Отвечай кратко, не более 10 слов. Отвечай на русском английскими символами ТРАНСЛИТОМ ."},
                {"role": "user", "content": text}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка Groq LLM: {e}")
        return "AI Error"

def recognize_whisper(wav_file_path):
    with open(wav_file_path, "rb") as audio_file:
        transcript = groq_client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=audio_file,
            language="ru"
        )
        return transcript.text

def save_raw_as_wav(raw_data, filename):
    """Сохраняет сырые PCM данные как WAV файл"""
    with wave.open(filename, 'wb') as wav_file:
        wav_file.setnchannels(1)  # моно
        wav_file.setsampwidth(2)  # 16 бит = 2 байта
        wav_file.setframerate(16000)  # 16kHz
        wav_file.writeframes(raw_data)

@app.get("/")
async def root():
    return {"status": "ok", "message": "Voice Assistant Server"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Клиент подключен")
    
    try:
        all_data = bytearray()
        
        while True:
            data = await websocket.receive_bytes()
            
            if b"END_STREAM" in data:
                all_data.extend(data.replace(b"END_STREAM", b""))
                break
            all_data.extend(data)
        
        print(f"Получено {len(all_data)} байт аудио")
        
        # Сохраняем как WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
            temp_filename = tmpfile.name
        
        save_raw_as_wav(bytes(all_data), temp_filename)
        
        # Распознавание
        text = recognize_whisper(temp_filename)
        print(f"Распознано: {text}")
        os.remove(temp_filename)
        
        # Ответ AI
        answer = get_groq_response(text)
        print(f"Ответ: {answer}")
        
        await websocket.send_text(answer)
        
    except Exception as e:
        print(f"Ошибка: {e}")
        await websocket.send_text("Error")
    finally:
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
