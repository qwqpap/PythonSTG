import miniaudio
try:
    decoded = miniaudio.decode_file("assets/audio/se/se_plst00.wav")
    print("type of decoded.samples:", type(decoded.samples))
except Exception as e:
    print(f"error: {e}")
