from flask import Flask, request, jsonify, send_from_directory
from pytube import YouTube
import os
import speech_recognition as sr
from googletrans import Translator
import moviepy.editor as mp
from datetime import timedelta

app = Flask(__name__)
translator = Translator()

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def format_srt_segment(index, start_time, end_time, text):
    return f"{index}\n{start_time} --> {end_time}\n{text}\n\n"

def seconds_to_srt_time(seconds):
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    millis = int((td.total_seconds() - total_seconds) * 1000)
    return f"{str(td)}.000".replace(".", ",")

@app.route('/translate', methods=['POST'])
def translate_video():
    try:
        data = request.json
        youtube_url = data.get('youtubeUrl')
        languages = data.get('languages', [])

        if not youtube_url:
            return jsonify({'error': 'YouTube URL is required'}), 400

        yt = YouTube(youtube_url)
        video_stream = yt.streams.filter(progressive=True, file_extension='mp4').first()
        video_path = os.path.join(UPLOAD_FOLDER, f'{yt.video_id}.mp4')
        video_stream.download(output_path=UPLOAD_FOLDER, filename=f'{yt.video_id}.mp4')

        audio_path = os.path.join(UPLOAD_FOLDER, f'{yt.video_id}.wav')
        video = mp.VideoFileClip(video_path)
        video.audio.write_audiofile(audio_path)

        recognizer = sr.Recognizer()
        audio_file = sr.AudioFile(audio_path)

        transcript_segments = []
        with audio_file as source:
            total_duration = int(source.DURATION)
            chunk_duration = 30
            index = 1
            offset = 0
            while offset < total_duration:
                source_audio = recognizer.record(source, duration=chunk_duration)
                try:
                    text = recognizer.recognize_google(source_audio)
                    start_time = seconds_to_srt_time(offset)
                    end_time = seconds_to_srt_time(min(offset + chunk_duration, total_duration))
                    transcript_segments.append((index, start_time, end_time, text))
                    index += 1
                except sr.UnknownValueError:
                    pass
                offset += chunk_duration

        translations = {lang: [] for lang in languages}
        for lang in languages:
            for seg in transcript_segments:
                translated = translator.translate(seg[3], dest=lang)
                translations[lang].append((seg[0], seg[1], seg[2], translated.text))

        srt_files = {}
        for lang, segments in translations.items():
            srt_content = ""
            for seg in segments:
                srt_content += format_srt_segment(*seg)
            srt_path = os.path.join(UPLOAD_FOLDER, f"subtitles_{lang}.srt")
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            srt_files[lang] = srt_content

        os.remove(video_path)
        os.remove(audio_path)

        return jsonify({
            'success': True,
            'videoId': yt.video_id,
            'title': yt.title,
            'translations': {lang: "Translated Successfully" for lang in languages},
            'srtFiles': srt_files
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Required for Vercel serverless deployment
def handler(event, context):
    from flask_lambda import FlaskLambda
    return FlaskLambda(app)(event, context)
