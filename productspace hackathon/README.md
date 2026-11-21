# Aftertone

## Your project

Independent podcast editors scrub entire interviews to find a short passage that makes sense to a stranger. A dramatic sentence often needs the line before it and the consequence after it. Aftertone ranks complete passages, explains the editorial signals, and remembers what a creator changes.

Team Context · Product Space Agentic AI Hackathon · Problem 01, Media: content repurposing studio with brand memory.

## Build plan

1. Ingest source media with timed English/Hindi captions or optional Sarvam transcription. Find distinct editorial directions and keep their evidence attached.
2. Give each creator a review desk with playable vertical exports, timed captions, platform copy and learned voice preferences.
3. Schedule approved clips, measure retention, re-rank subsequent episodes and package a downloadable studio.

The design draws on [Sharkyclips](https://github.com/utkualsir/sharkyclips) for the export-to-publishing workflow, [auto-video-editor](https://github.com/kiy0ni/auto-video-editor) for highlight scoring, [Chopify](https://github.com/mehbul/chopify) for the browser and subtitle workflow, and [stream-clipper](https://github.com/sidgaikwad/stream-clipper) for temporal peak selection. The implementation here is original. REA inspection covered AutoClip’s public web client. Its server-side ranking is private.

## Run the studio

Use Python 3.11–3.14 on macOS or Linux. From the extracted Aftertone folder:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open http://localhost:8787. The original narrated demo and its timed transcript are bundled. For uploads without captions, select English or Hindi: the first run downloads the matching Vosk model (roughly 40 MB). Subsequent transcriptions run offline. Auto uses English in offline mode. Use a matching SRT or enable Sarvam for mixed-language recordings. FFmpeg is included through imageio-ffmpeg. On Linux install Noto Devanagari fonts for Hindi subtitle rendering.

For a persistent web host with Docker and an HTTPS reverse proxy:

```sh
docker build -t aftertone .
docker run --restart unless-stopped -p 8787:8787 -v aftertone-data:/studio/data aftertone
```

Keep one application process running. Workspaces use a signed browser cookie, so use the same browser and hostname to return to your work. Uploaded sources, exports, the SQLite database and offline models live in the data volume. Back up the volume and restrict host access, especially when channel refresh tokens are present. The studio ZIP under Download studio contains the application, original demo and setup files.

## Demo in two minutes

1. Paste a public HTTPS media file or YouTube video link, select a running time from 30 to 180 seconds, and find directions. For a key-free narrated demo, open **Project brief** and choose **Find a cut in this narration**. Review a direction, click its story beats to audition the source, and finalize it to unlock captioned MP4 and SRT exports.
2. Switch to Instagram to preview shorter on-screen caption phrases, rewrite the copy in a short lowercase voice, then save. Open a different moment on Instagram to see the learned style. Brand memory counts saved edits.
3. Choose a time in Plan publication. The calendar stores the approved platform and exact copy. Posting is opt-in per clip.
4. Record the observed average percentage viewed for a clip. Return to Clip studio and re-rank. The rationale shows the retention adjustment, which also applies to subsequent imports.
5. Import a podcast or video with English or Hindi audio. The same pipeline runs on real uploads. A matching SRT skips transcription. The single-process build accepts up to 512 MiB and three hours per recording. Upload speed, transcript density and host CPU affect processing time.

## Inside the hardest part

Aftertone scores fixed-duration windows anchored at cue beginnings and endings. It penalizes silence and partial phrases and limits overlap between selected directions. The editor can re-run a recording at any whole-second length from 30 to 180 seconds. VADER sentiment and Hindi/Hinglish cues describe the emotional trajectory. The audio pass measures RMS energy every 200 milliseconds. Per-line changes in delivery, pauses, and unfinished endings also affect selection. Each thumbnail shows the measured audio envelope. Discovery language, specificity, a resolving line, duration and promotional filler affect the score. The score is an editorial heuristic on a 1–99 scale. Reported retention modifies the ranking for the same arc with shrinkage for small sample counts. The display gives source evidence for inspection; sarcasm, translation errors and noisy audio still need human judgment.

Brand memory learns platform-specific word count, casing and hashtag choices from edits. With Sarvam enabled, recent before-and-after examples also condition an editorial pass. Orthogonal export and publishing steps keep a download independent of any social account.

## Optional services

Copy .env.example to .env and restart after changing settings.

- **ElevenLabs** supplies the bundled George narration on the Project brief page. For custom narrated MP4 downloads, set ELEVENLABS_API_KEY and optionally ELEVENLABS_VOICE_ID. After finalizing, Generate ElevenLabs voiceover sends the selected transcript to the service. Returned character timing aligns the voice to the caption cues. The normal export and YouTube scheduler use the original source audio.
- **Link imports** require curl for direct HTTPS media and yt-dlp for public YouTube videos. The Docker image includes both. Private, restricted, and unsupported player pages require a file upload.
- **Sarvam** uses SARVAM_API_KEY. Opt in per import to send audio for transcription when needed, and selected text plus recent voice examples for editorial review. The editor accepts only suggestions that cite a source phrase, validates the returned identifiers, and falls back to local ranking if the editorial service fails.
- **YouTube** requires a Google Cloud web OAuth client with YouTube Data API v3 enabled. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and PUBLIC_URL. Register PUBLIC_URL/youtube/callback as the exact redirect URI. Connect the intended channel from Plan publication. The scheduler uploads only explicitly enabled YouTube items and requests public visibility. Google can restrict visibility for unverified projects. Calendar-only items never upload. The server must be running when the item is due, and processes overdue scheduled items on restart. Check YouTube Studio before rescheduling an interrupted upload.
- **Performance** uses creator-entered retention from platform analytics. Cross-platform account analytics synchronization is outside this build.

Official references: [Vosk models](https://alphacephei.com/vosk/models), [Sarvam transcription](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe), [Sarvam chat](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1), [YouTube video upload](https://developers.google.com/youtube/v3/docs/videos/insert).

## Motion films

Project brief includes a 36-second Jessica-narrated film, its vertical adaptation, and a 30-second studio export. The source project, timed script, storyboard, font licenses, and rendering commands are in [motion/README.md](motion/README.md). New source exports use kinetic caption highlights and audio-only recordings include a live waveform.
