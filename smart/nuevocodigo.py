# receptor_bpm_serial.py
import serial

ser = serial.Serial("COM6", 115200, timeout=1)  # cambia COM3 según tu PC
while True:
    line = ser.readline().strip()
    if not line:
        continue
    try:
        print(int(line))   # si Arduino envía SOLO el BPM por línea
    except:
        # si Arduino manda varias columnas, probá tomar la última:
        try:
            print(int(line.split()[-1]))
        except:
            pass
