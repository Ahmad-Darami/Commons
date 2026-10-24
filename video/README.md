# Rendering the walkthrough video

The video is a scripted run of the real prototype (`../prototype/index.html`) in headless Chromium. `director.js` poses the scene and adds captions for each moment. `capture.js` freezes the page clock, advances it 1/30 s at a time, and screenshots every frame, so playback stays smooth however slow the machine is.

```bash
npm i playwright                       # uses Playwright's Chromium
node capture.js frames 30              # 1800 JPEG frames at 1920×1080
python3 music.py music.wav             # 60 s ambient bed (needs numpy)
ffmpeg -framerate 30 -i frames/f%05d.jpg -i music.wav \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -preset slow -c:a aac -b:a 160k -af volume=0.75 \
  -shortest -movflags +faststart commons-walkthrough.mp4
```

- Preview single moments before a full render: `node capture.js stills 30 12,27,40`
- To edit captions, timing or the end card, change `CAPS`, the `at(...)` cues and the `#cEnd` block in `director.js`.
- Offline: set `THREE_DIR` to a local `three@0.128.0` package so the CDN isn't needed.
