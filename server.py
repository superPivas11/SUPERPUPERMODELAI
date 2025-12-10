import os
import tempfile
import wave
from fastapi import FastAPI, WebSocket
from groq import Groq
import uvicorn

# --- НАСТРОЙКИ ---
PORT = int(os.environ.get("PORT", 10000))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

app = FastAPI()

# Проверяем доступность API ключа
print(f"DEBUG: API Key exists: {bool(GROQ_API_KEY)}")
if not GROQ_API_KEY or GROQ_API_KEY == "your-api-key-here":
    print("ERROR: Please set GROQ_API_KEY environment variable")

# Инициализируем клиент Groq (новый синтаксис)
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("DEBUG: Groq client initialized successfully")
except Exception as e:
    print(f"ERROR: Failed to initialize Groq client: {e}")
    groq_client = None

def get_groq_response(text):
    """Получение ответа от LLM"""
    try:
        if not text or text.strip() == "":
            return "Не расслышал, повторите пожалуйста"
        
        if not groq_client:
            return "Ошибка: сервис временно недоступен"
            
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты голосовой ассистент. Отвечай кратко, 1-2 предложения на русском языке."},
                {"role": "user", "content": text}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка Groq LLM: {e}")
        return "Извините, произошла ошибка"

def recognize_whisper(wav_file_path):
    """Распознавание речи через Whisper"""
    try:
        if not groq_client:
            return ""
            
        with open(wav_file_path, "rb") as audio_file:
            transcript = groq_client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=audio_file,
                language="ru",
                response_format="text",
                temperature=0.0
            )
            print(f"DEBUG: Распознанный текст: '{transcript}'")
            return transcript
    except Exception as e:
        print(f"Ошибка распознавания: {e}")
        return ""

def save_raw_as_wav(raw_data, filename):
    """Сохраняет сырые PCM данные как WAV файл"""
    try:
        # Проверяем, достаточно ли данных
        if len(raw_data) < 3200:
            print(f"DEBUG: Слишком мало аудиоданных: {len(raw_data)} байт")
            return False
            
        with wave.open(filename, 'wb') as wav_file:
            wav_file.setnchannels(1)  # моно
            wav_file.setsampwidth(2)  # 16 бит = 2 байта
            wav_file.setframerate(16000)  # 16kHz
            wav_file.writeframes(raw_data)
        
        print(f"DEBUG: Сохранено {len(raw_data)} байт в WAV файл")
        return True
    except Exception as e:
        print(f"Ошибка сохранения WAV: {e}")
        return False

@app.get("/")
async def root():
    return {"status": "ok", "message": "Voice Assistant Server"}

@app.get("/test")
async def test():
    """Тестовый эндпоинт для проверки работы"""
    try:
        test_text = "Привет, как дела?"
        response = get_groq_response(test_text)
        return {
            "status": "ok",
            "groq_client_initialized": groq_client is not None,
            "test_response": response
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Клиент подключен")
    
    try:
        all_data = bytearray()
        
        # Ждем данные от ESP32
        while True:
            # Получаем байты
            data = await websocket.receive_bytes()
            print(f"DEBUG: Получено {len(data)} байт")
            
            # Проверяем, не является ли это сигналом окончания
            if b"END_STREAM" in data:
                # Убираем маркер конца из данных
                audio_data = data.replace(b"END_STREAM", b"")
                all_data.extend(audio_data)
                print(f"DEBUG: Получен END_STREAM, всего данных: {len(all_data)} байт")
                break
                
            all_data.extend(data)
        
        # Проверяем, получили ли мы хоть какие-то данные
        if len(all_data) == 0:
            print("DEBUG: Не получено аудиоданных")
            await websocket.send_text("Не получено аудиоданных")
            await websocket.close()
            return
        
        print(f"DEBUG: Всего получено {len(all_data)} байт аудио")
        
        # Сохраняем как WAV во временный файл
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
            temp_filename = tmpfile.name
        
        # Сохраняем аудио в WAV
        if not save_raw_as_wav(bytes(all_data), temp_filename):
            await websocket.send_text("Ошибка: не удалось сохранить аудио")
            await websocket.close()
            return
        
        # Распознавание речи
        print(f"DEBUG: Отправляем файл {temp_filename} в Whisper...")
        text = recognize_whisper(temp_filename)
        
        # Удаляем временный файл
        try:
            os.remove(temp_filename)
        except:
            pass
        
        # Проверяем результат распознавания
        if not text or text.strip() == "":
            print("DEBUG: Whisper вернул пустой текст")
            await websocket.send_text("Не удалось распознать речь. Попробуйте говорить четче.")
        else:
            print(f"DEBUG: Распознано: '{text}'")
            
            # Получаем ответ от AI
            answer = get_groq_response(text)
            print(f"DEBUG: Ответ AI: '{answer}'")
            
            await websocket.send_text(answer)
        
    except Exception as e:
        print(f"Ошибка в WebSocket: {e}")
        try:
            await websocket.send_text("Ошибка сервера")
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
        print("Соединение закрыто")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
