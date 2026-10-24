"""Synthesizes a soft 60 s ambient bed (pad + gentle arpeggio) timed to the video's scenes."""
import numpy as np, wave, sys

SR, DUR = 48000, 60.0
t = np.arange(int(SR * DUR)) / SR
out = np.zeros((2, t.size))
f = lambda m: 440.0 * 2 ** ((m - 69) / 12)

CH = {  # bass, pad voicing (MIDI)
    'F':  (41, [57, 60, 64, 67]),
    'Am': (45, [55, 60, 64, 69]),
    'C':  (48, [59, 60, 64, 67]),
    'G':  (43, [55, 59, 62, 69]),
}
SEQ = ['F', 'Am', 'C', 'G', 'F', 'Am', 'G', 'C']
L = DUR / len(SEQ)

def env(n, a, r):
    e = np.ones(n); ai, ri = int(a * SR), int(r * SR)
    e[:ai] = np.linspace(0, 1, ai) ** 2; e[-ri:] *= np.linspace(1, 0, ri) ** 1.5
    return e

def add(sig, start, pan=0.0):
    i = int(start * SR); j = min(t.size, i + sig.size); sig = sig[: j - i]
    out[0, i:j] += sig * np.sqrt(0.5 * (1 - pan)); out[1, i:j] += sig * np.sqrt(0.5 * (1 + pan))

rng = np.random.default_rng(3)
for k, name in enumerate(SEQ):
    bass, pad = CH[name]
    start = k * L; n = int((L + 2.2) * SR); tt = np.arange(n) / SR
    e = env(n, 1.8, 2.4)
    for idx, m in enumerate(pad):
        for det, pan in ((-0.0018, -0.6), (0.0018, 0.6)):
            fr = f(m) * (1 + det)
            s = np.sin(2 * np.pi * fr * tt + rng.uniform(0, 6)) + 0.18 * np.sin(4 * np.pi * fr * tt)
            add(0.035 * s * e * (1 + 0.15 * np.sin(2 * np.pi * 0.17 * tt + idx)), start, pan * (0.4 + 0.15 * idx))
    add(0.09 * np.sin(2 * np.pi * f(bass) * tt) * e, start)

# arpeggio: enters as the room is scanned, rests on the end card
STEP = 60 / 96 / 2
a_t = 11.0
while a_t < 53.0:
    k = int(a_t // L); bass, pad = CH[SEQ[k]]
    notes = [m + 12 for m in pad] + [pad[1] + 24]
    beat = int(round((a_t - 11.0) / STEP))
    m = notes[[0, 1, 2, 3, 4, 3, 2, 1][beat % 8]]
    n = int(1.6 * SR); tt = np.arange(n) / SR
    level = 0.05 * min(1, (a_t - 11) / 4) * (0.55 if a_t > 35.4 and a_t < 46 else 1)
    s = (np.sin(2 * np.pi * f(m) * tt) + 0.25 * np.sin(6 * np.pi * f(m) * tt) * np.exp(-tt * 9)) * np.exp(-tt * 3.2)
    s[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
    add(level * s, a_t, 0.35 * np.sin(beat * 0.7))
    a_t += STEP

# reverb: convolve with a decaying-noise impulse response
ir_n = int(2.8 * SR); irt = np.arange(ir_n) / SR
for c in range(2):
    ir = rng.standard_normal(ir_n) * np.exp(-irt * 2.3); ir[0] = 0; ir /= np.abs(ir).sum() / 6
    N = 1 << int(np.ceil(np.log2(t.size + ir_n)))
    wet = np.fft.irfft(np.fft.rfft(out[c], N) * np.fft.rfft(ir, N), N)[: t.size]
    out[c] = 0.75 * out[c] + 0.35 * wet

fade = np.ones(t.size); fi, fo = int(1.5 * SR), int(3.5 * SR)
fade[:fi] = np.linspace(0, 1, fi); fade[-fo:] = np.linspace(1, 0, fo) ** 1.4
out *= fade
out *= 0.5 / np.abs(out).max()
pcm = (np.clip(out.T, -1, 1) * 32767).astype('<i2')
with wave.open(sys.argv[1], 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
