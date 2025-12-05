import socket
import speech_recognition as sr # Используется только для форматирования
from pydub import AudioSegment
import io
import tempfile
import os

from groq import Groq

# --- НАСТРОЙКИ ---
HOST = '0.0.0.0'
PORT = 8080
# !!! КЛЮЧ GROQ (для ответа AI и Whisper) !!!
GROQ_API_KEY = "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" 

# Инициализируем клиент Groq
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
except Exception as e:
    print(f"Ошибка инициализации клиента Groq (проверьте ключ): {e}")
    exit()

def get_groq_response(text):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # Мощная модель Groq
            messages=[
                {"role": "system", "content": "Ты голосовой ассистент. Отвечай очень кратко, не более 10 слов, СТРОГО только латинскими буквами (транслитом)."},
                {"role": "user", "content": text}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка Groq LLM: {e}")
        return f"AI Error: Groq failed." 

def recognize_whisper(wav_file_path):
    """Использует Groq Whisper для распознавания аудиофайла."""
    with open(wav_file_path, "rb") as audio_file:
        transcript = groq_client.audio.transcriptions.create(
            model="whisper-large-v3",  # Бесплатный Whisper от Groq
            file=audio_file,
            language="ru"
        )
        return transcript.text

def convert_raw_to_wav(raw_data):
    audio = AudioSegment(
        data=raw_data,
        sample_width=2, 
        frame_rate=16000,
        channels=1
    )
    wav_io = io.BytesIO()
    audio.export(wav_io, format="wav") 
    wav_io.seek(0)
    return audio

def run_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"Сервер запущен на порту {PORT}.")
        
        while True:
            print("Ожидание подключения...")
            conn, addr = s.accept()
            with conn:
                print(f"Подключен: {addr}")
                all_data = bytearray()
                
                while True:
                    data = conn.recv(4096)
                    if not data: break
                    
                    if b"END_STREAM" in data:
                        all_data.extend(data.replace(b"END_STREAM", b""))
                        break
                    all_data.extend(data)
                
                print(f"Получено {len(all_data)} байт аудио.")
                
                answer = "Error"
                
                # --- НОВАЯ ЛОГИКА ASR ---
                try:
                    audio_segment = convert_raw_to_wav(all_data)
                    # Сохраняем во временный файл для Whisper
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
                        audio_segment.export(tmpfile.name, format="wav")
                        temp_filename = tmpfile.name
                    
                    # Распознавание через Whisper
                    text = recognize_whisper(temp_filename)
                    print(f"Распознано (Whisper): {text}")
                    
                    # Удаляем временный файл
                    os.remove(temp_filename)
                        
                    # Запрос к AI (Groq)
                    answer = get_groq_response(text)
                    print(f"Ответ AI: {answer}")
                        
                except sr.UnknownValueError:
                    print("Не удалось распознать звук (UnknownValueError)")
                    answer = "Ne ponyal..."
                except Exception as e:
                    print(f"Критическая ошибка в обработке: {e}")
                    answer = f"Python error: check server console."
                    
                conn.sendall(answer.encode('utf-8'))

if __name__ == "__main__":
    run_server()