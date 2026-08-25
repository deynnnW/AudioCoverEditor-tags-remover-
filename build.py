import os
import subprocess
import sys

def build_exe():
    print("=== Начало сборки AudioCoverEditor.exe (Onefile) ===")
    
    icon_arg = "--icon=assets/icon.ico" if os.path.exists("assets/icon.ico") else ""

    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        icon_arg,
        "--name=AudioCoverEditor",
        "--add-data=assets;assets",
        "--collect-all=customtkinter",
        "--collect-all=tkinterdnd2",
        "--collect-all=mutagen",
        "--collect-all=PIL",
        "app.py"
    ]
    cmd = [c for c in cmd if c]

    print("Выполнение команды:", " ".join(cmd))
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print("Ошибка сборки!")
        sys.exit(res.returncode)

    exe_path = os.path.abspath("dist/AudioCoverEditor.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print("\n[OK] СБОРКА УСПЕШНО ЗАВЕРШЕНА!")
        print(f"Исполняемый файл: {exe_path}")
        print(f"Размер файла: {size_mb:.2f} MB")
    else:
        print("Файл dist/AudioCoverEditor.exe не найден!")

if __name__ == "__main__":
    build_exe()
