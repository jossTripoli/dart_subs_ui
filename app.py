import os
import tempfile
from flask import Flask, request, send_file, render_template, jsonify
from werkzeug.utils import secure_filename
import ffmpeg
import whisper

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB limit

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

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
        ffmpeg.input(filepath).output(audio_path, acodec="pcm_s16le", ac=1, ar="16k").run(quiet=True, overwrite_output=True)

        # Generate subtitles
        model = whisper.load_model("small")
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
        ffmpeg.concat(
            ffmpeg.input(filepath).filter('subtitles', srt_path, force_style="OutlineColour=&H40000000,BorderStyle=3"),
            ffmpeg.input(filepath).audio,
            v=1, a=1
        ).output(output_path).run(quiet=True, overwrite_output=True)

        return jsonify({
            'message': 'Subtitles generated successfully',
            'srt_file': f"{os.path.splitext(filename)[0]}.srt",
            'video_file': f"{os.path.splitext(filename)[0]}_subtitled.mp4"
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)

def format_timestamp(seconds):
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    seconds = seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"

if __name__ == '__main__':
    app.run(debug=True)
