import miniaudio
import inspect
with open("miniaudio_info.txt", "w", encoding="utf-8") as f:
    f.write("dir:\n")
    f.write(str(dir(miniaudio)) + "\n")
    if hasattr(miniaudio, "decode_file"):
        f.write("\ndecode_file doc:\n")
        f.write(str(miniaudio.decode_file.__doc__) + "\n")
        try:
            f.write("\nsignature:\n")
            f.write(str(inspect.signature(miniaudio.decode_file)) + "\n")
        except Exception as e:
            f.write(f"\nsig error: {e}\n")
    if hasattr(miniaudio, "decode"):
        f.write("\ndecode doc:\n")
        f.write(str(miniaudio.decode.__doc__) + "\n")
