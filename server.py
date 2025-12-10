import os
import tempfile
import wave
import struct
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq

# --- НАСТРОЙКИ ---
PORT = int(os.environ.get("PORT", 8080))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

app = FastAPI()

# Добавляем CORS middleware для веб-сокетов
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализируем клиент Groq
groq_client = Groq(api_key=GROQ_API_KEY)

def get_groq_response(text):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты голосовой ассистент. Отвечай кратко, около 10 слов на русском языке. Не используй какие-либо иные знаки кроме стандартных. Если просят назвать дату - пиши числами. Если попросят решить пример - отвечай также числами."},
                {"role": "user", "content": text}
            ],
            max_tokens=100,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка Groq LLM: {e}")
        return "Произошла ошибка при обработке запроса"

def recognize_whisper(wav_file_path):
    try:
        with open(wav_file_path, "rb") as audio_file:
            transcript = groq_client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                language="ru",
                response_format="text"
            )
            return transcript
    except Exception as e:
        print(f"Ошибка распознавания речи: {e}")
        return ""

def save_raw_as_wav(raw_data, filename):
    """Сохраняет сырые PCM данные как WAV файл"""
    try:
        with wave.open(filename, 'wb') as wav_file:
            wav_file.setnchannels(1)  # моно
            wav_file.setsampwidth(2)  # 16 бит = 2 байта
            wav_file.setframerate(16000)  # 16kHz
            wav_file.writeframes(raw_data)
        return True
    except Exception as e:
        print(f"Ошибка сохранения WAV файла: {e}")
        return False

@app.get("/")
async def root():
    return {"status": "ok", "message": "Voice Assistant Server"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Клиент подключен")
    
    try:
        all_data = bytearray()
        
        while True:
            # Получаем данные от клиента
            message = await websocket.receive()
            
            if "bytes" in message:
                data = message["bytes"]
                # Проверяем, не является ли это сигналом окончания
                if data == b"END_STREAM":
                    break
                all_data.extend(data)
            elif "text" in message:
                text = message["text"]
                if text == "END_STREAM":
                    break
                else:
                    # Если пришел текст вместо аудио
                    await websocket.send_text(f"Получен текст: {text}")
        
        if len(all_data) == 0:
            await websocket.send_text("Не получено аудиоданных")
            await websocket.close()
            return
        
        print(f"Получено {len(all_data)} байт аудио")
        
        # Сохраняем как WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
            temp_filename = tmpfile.name
        
        if not save_raw_as_wav(bytes(all_data), temp_filename):
            await websocket.send_text("Ошибка обработки аудио")
            await websocket.close()
            return
        
        # Распознавание
        text = recognize_whisper(temp_filename)
        
        # Удаляем временный файл
        try:
            os.remove(temp_filename)
        except:
            pass
        
        if not text or text.strip() == "":
            print("Не удалось распознать речь")
            await websocket.send_text("Не удалось распознать речь. Попробуйте еще раз.")
        else:
            print(f"Распознано: {text}")
            
            # Ответ AI
            answer = get_groq_response(text)
            print(f"Ответ: {answer}")
            
            await websocket.send_text(answer)
        
    except Exception as e:
        print(f"Ошибка в WebSocket: {e}")
        try:
            await websocket.send_text(f"Ошибка сервера: {str(e)}")
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
        print("Соединение закрыто")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, ws_ping_interval=20, ws_ping_timeout=20)
