import wave
import array
from math import sin, pi

amp = [sin(theta * 2 * pi) if theta < 1 else 0
    for theta in (i / 2000 for i in range(16000))]
dig = [sin(theta * 2 * pi) for theta in (i / 36.36 for i in range(16000))]
sig = [ai * di for ai, di in zip(amp, dig)]
print(min(sig), max(sig))
sig = array.array('h', (round(i * 32767) for i in sig))
with wave.open("beeps.wav", "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(memoryview(sig))
    w.writeframes(memoryview(sig))
    w.writeframes(memoryview(sig))
    w.writeframes(memoryview(sig))
    w.writeframes(memoryview(sig))
    w.writeframes(memoryview(sig))
    w.writeframes(memoryview(sig))
    w.writeframes(memoryview(sig))
    w.writeframes(memoryview(sig))
    w.writeframes(memoryview(sig))
