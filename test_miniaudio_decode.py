import miniaudio
try:
    print("Testing str...")
    miniaudio.decode_file("assets/audio/se/se_plst00.wav")
    print("str OK!")
except Exception as e:
    print(f"str failed: {e}")

try:
    print("Testing bytes...")
    miniaudio.decode_file(b"assets/audio/se/se_plst00.wav")
    print("bytes OK!")
except Exception as e:
    print(f"bytes failed: {e}")
