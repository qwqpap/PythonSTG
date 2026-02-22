import miniaudio
try:
    gen = miniaudio.stream_file("assets/audio/music/00.wav")
    chunk1 = next(gen)
    print(f"next(gen) len: {len(chunk1)}")
    chunk2 = gen.send(512)
    print(f"gen.send(512) len: {len(chunk2)}")
    chunk3 = gen.send(100)
    print(f"gen.send(100) len: {len(chunk3)}")
except Exception as e:
    print(f"error: {e}")
