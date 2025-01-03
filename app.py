import os
import tempfile
import subprocess
import shlex
from flask import Flask, request, send_file, render_template, jsonify
from werkzeug.utils import secure_filename
import whisper

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB limit

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

SUPPORTED_LANGUAGES = {
    'eng': 'English',
    'chi': 'Chinese',
    'spa': 'Spanish',
    'por': 'Portuguese',
    'fre': 'French',
    'ita': 'Italian',
    'gre': 'Greek',
    'pol': 'Polish'
}

FONT_PATH = os.path.abspath("static/fonts/NotoSansSC-Regular.ttf")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html', languages=SUPPORTED_LANGUAGES)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return jsonify({'message': 'File uploaded successfully', 'filename': filename})
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/generate', methods=['POST'])
def generate_subtitles():
    filename = request.json.get('filename')
    if not filename:
        return jsonify({'error': 'No filename provided'}), 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    try:
        # Extract audio
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{os.path.splitext(filename)[0]}.wav")
        subprocess.run(['ffmpeg', '-y', '-i', filepath, '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_path], check=True)

        # Generate subtitles
        model = whisper.load_model("tiny")
        result = model.transcribe(audio_path)

        # Write SRT file
        srt_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{os.path.splitext(filename)[0]}.srt")
        with open(srt_path, "w", encoding="utf-8") as srt:
            for i, segment in enumerate(result["segments"], start=1):
                print(f"{i}\n"
                      f"{format_timestamp(segment['start'])} --> {format_timestamp(segment['end'])}\n"
                      f"{segment['text'].strip()}\n",
                      file=srt)

        # Burn subtitles into video
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{os.path.splitext(filename)[0]}_subtitled.mp4")
        
        ffmpeg_command = [
            'ffmpeg', '-y', '-i', filepath, 
            '-vf', f"subtitles='{shlex.quote(srt_path)}':force_style='Fontsize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H40000000,BorderStyle=3'",
            '-c:a', 'copy',
            '-y', output_path
        ]

        subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)

        return jsonify({
            'message': 'Subtitles generated successfully',
            'srt_file': f"{os.path.splitext(filename)[0]}.srt",
            'video_file': f"{os.path.splitext(filename)[0]}_subtitled.mp4"
        })
    except subprocess.CalledProcessError as e:
        return jsonify({'error': f"FFmpeg error: {e.stderr}"}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)

@app.route('/upload-with-srt', methods=['POST'])
def upload_with_srt():
    if 'video' not in request.files or 'srt' not in request.files:
        return jsonify({'error': 'Missing video or SRT file'}), 400
    
    video_file = request.files['video']
    srt_file = request.files['srt']
    language = request.form.get('language', 'eng')
    
    if video_file.filename == '' or srt_file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if video_file and allowed_file(video_file.filename) and srt_file.filename.lower().endswith('.srt'):
        video_filename = secure_filename(video_file.filename)
        srt_filename = secure_filename(srt_file.filename)
        
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
        srt_path = os.path.join(app.config['UPLOAD_FOLDER'], srt_filename)
        
        video_file.save(video_path)
        srt_file.save(srt_path)
        
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{os.path.splitext(video_filename)[0]}_subtitled.mp4")

        try:
            ffmpeg_command = [
                'ffmpeg', '-y', '-i', video_path, 
                '-vf', f"subtitles='{shlex.quote(srt_path)}':force_style='Fontsize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H40000000,BorderStyle=3'",
                '-c:a', 'copy',
                '-y', output_path
            ]

            subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
            
            return jsonify({
                'message': 'Video with subtitles generated successfully',
                'video_file': f"{os.path.splitext(video_filename)[0]}_subtitled.mp4"
            })
        except subprocess.CalledProcessError as e:
            return jsonify({'error': f"FFmpeg error: {e.stderr}"}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/generate-srt', methods=['POST'])
def generate_srt():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file'}), 400
    
    video_file = request.files['video']
    
    if video_file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if video_file and allowed_file(video_file.filename):
        video_filename = secure_filename(video_file.filename)
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
        video_file.save(video_path)
        
        try:
            # Extract audio
            audio_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{os.path.splitext(video_filename)[0]}.wav")
            subprocess.run(['ffmpeg', '-y', '-i', video_path, '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_path], check=True)
            
            # Generate subtitles
            model = whisper.load_model("tiny")
            result = model.transcribe(audio_path)
            
            # Write SRT file
            srt_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{os.path.splitext(video_filename)[0]}.srt")
            with open(srt_path, "w", encoding="utf-8") as srt:
                for i, segment in enumerate(result["segments"], start=1):
                    print(f"{i}\n"
                          f"{format_timestamp(segment['start'])} --> {format_timestamp(segment['end'])}\n"
                          f"{segment['text'].strip()}\n",
                          file=srt)
            
            # Burn subtitles into video
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{os.path.splitext(video_filename)[0]}_subtitled.mp4")
            ffmpeg_command = [
                'ffmpeg', '-y', '-i', video_path, 
                '-vf', f"subtitles='{shlex.quote(srt_path)}':force_style='Fontsize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H40000000,BorderStyle=3'",
                '-c:a', 'copy',
                '-y', output_path
            ]

            subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
            
            return jsonify({
                'message': 'Subtitles generated and video created successfully',
                'srt_file': f"{os.path.splitext(video_filename)[0]}.srt",
                'video_file': f"{os.path.splitext(video_filename)[0]}_subtitled.mp4"
            })
        except subprocess.CalledProcessError as e:
            return jsonify({'error': f"FFmpeg error: {e.stderr}"}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Invalid file type'}), 400

def format_timestamp(seconds):
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    seconds = seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"

if __name__ == '__main__':
    app.run(debug=True)

