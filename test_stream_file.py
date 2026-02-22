import miniaudio
try:
    gen = miniaudio.stream_file("assets/audio/se/se_plst00.wav")
    chunk1 = next(gen)
    print(f"next(gen) chunk type: {type(chunk1)}, len: {len(chunk1) if chunk1 else 'None'}")
    chunk2 = gen.send(1024)
    print(f"gen.send(1024) chunk type: {type(chunk2)}, len: {len(chunk2) if chunk2 else 'None'}")
except Exception as e:
    print(f"error: {e}")
