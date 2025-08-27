import socket, threading, time, json, re, os
from datetime import datetime
from flask import Flask, render_template, jsonify, request
import csv

app = Flask(__name__)

bpm_data = {'bpm': 0, 'timestamp': None, 'client_addr': None}

HOST = '0.0.0.0'
PORT = 8888   # <-- AJUSTA si tu .ino usa 5055

# Crear carpeta para historiales si no existe
HISTORIAL_DIR = 'historiales'
if not os.path.exists(HISTORIAL_DIR):
    os.makedirs(HISTORIAL_DIR)

def parse_bpm(msg: str):
    # Acepta {"bpm":72} o un número suelto en el texto
    try:
        j = json.loads(msg)
        if 'bpm' in j:
            v = int(j['bpm'])
            if 20 <= v <= 220: return v
    except: pass
    m = re.search(r'\b(\d{2,3})\b', msg)
    if m:
        v = int(m.group(1))
        if 20 <= v <= 220: return v
    return 0

def udp_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((HOST, PORT))
    print(f"[UDP] escuchando en {HOST}:{PORT}")
    try:
        while True:
            data, addr = sock.recvfrom(4096)
            msg = data.decode(errors='ignore').strip()
            bpm = parse_bpm(msg)
            bpm_data['bpm'] = bpm
            bpm_data['timestamp'] = datetime.now().strftime("%H:%M:%S")
            bpm_data['client_addr'] = f"{addr[0]}:{addr[1]}"
            if bpm > 0:
                print(f"BPM: {bpm}")
    except Exception as e:
        print("[UDP] error:", e)
    finally:
        sock.close()
        print("[UDP] cerrado")

def calcular_calorias(bpm, edad, peso, genero, duracion_min):
    """
    Calcula calorías quemadas aproximadas basado en BPM promedio
    Fórmula aproximada basada en estudios de gasto calórico
    """
    # Factores de corrección por género
    factor_genero = 1.0 if genero.lower() == 'masculino' else 0.9
    
    # Cálculo basado en zona de frecuencia cardíaca
    fcm = 220 - edad  # Frecuencia cardíaca máxima
    porcentaje_fcm = (bpm / fcm) * 100
    
    # Base metabólica por minuto (aproximada)
    if porcentaje_fcm < 60:
        factor_intensidad = 0.5
    elif porcentaje_fcm < 70:
        factor_intensidad = 0.7
    elif porcentaje_fcm < 80:
        factor_intensidad = 1.0
    elif porcentaje_fcm < 90:
        factor_intensidad = 1.3
    else:
        factor_intensidad = 1.6
    
    # Cálculo aproximado: peso * factor_intensidad * factor_género * duración
    calorias = peso * factor_intensidad * factor_genero * duracion_min * 0.1
    
    return round(calorias, 1)

def guardar_sesion(datos_sesion):
    """Guarda la sesión en un archivo CSV"""
    fecha_archivo = datetime.now().strftime("%Y-%m-%d")
    archivo_csv = os.path.join(HISTORIAL_DIR, f"sesiones_{fecha_archivo}.csv")
    
    # Verificar si el archivo existe para escribir headers
    archivo_existe = os.path.exists(archivo_csv)
    
    with open(archivo_csv, 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        # Escribir headers si es un archivo nuevo
        if not archivo_existe:
            writer.writerow([
                'Fecha', 'Hora Inicio', 'Hora Fin', 'Usuario', 'Edad', 'Género', 
                'Peso', 'Altura', 'Duración (min)', 'BPM Promedio', 'BPM Min', 
                'BPM Max', 'Lecturas Totales', 'Calorías Quemadas'
            ])
        
        # Escribir datos de la sesión
        writer.writerow([
            datos_sesion['fecha'],
            datos_sesion['hora_inicio'],
            datos_sesion['hora_fin'],
            datos_sesion['usuario'],
            datos_sesion['edad'],
            datos_sesion['genero'],
            datos_sesion['peso'],
            datos_sesion['altura'],
            datos_sesion['duracion'],
            datos_sesion['bpm_promedio'],
            datos_sesion['bpm_min'],
            datos_sesion['bpm_max'],
            datos_sesion['lecturas_totales'],
            datos_sesion['calorias']
        ])
    
    print(f"Sesión guardada en: {archivo_csv}")

def obtener_historial():
    """Obtiene todas las sesiones guardadas"""
    historial = []
    
    # Buscar todos los archivos CSV en la carpeta historiales
    if os.path.exists(HISTORIAL_DIR):
        for archivo in os.listdir(HISTORIAL_DIR):
            if archivo.startswith('sesiones_') and archivo.endswith('.csv'):
                ruta_archivo = os.path.join(HISTORIAL_DIR, archivo)
                try:
                    with open(ruta_archivo, 'r', encoding='utf-8') as file:
                        reader = csv.DictReader(file)
                        for fila in reader:
                            historial.append(fila)
                except Exception as e:
                    print(f"Error leyendo {archivo}: {e}")
    
    # Ordenar por fecha y hora (más recientes primero)
    historial.sort(key=lambda x: f"{x['Fecha']} {x['Hora Inicio']}", reverse=True)
    return historial

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sesion')
def sesion():
    return render_template('session_monitor.html')

@app.route('/historial')
def historial():
    return render_template('historial.html')

@app.route('/inicio')
def inicio():
    return render_template('inicio.html')

@app.route('/api/bpm')
def get_bpm():
    return jsonify(bpm_data)

@app.route('/api/calcular-calorias', methods=['POST'])
def calcular_calorias_api():
    datos = request.json
    
    calorias = calcular_calorias(
        datos['bpm_promedio'],
        datos['edad'],
        datos['peso'],
        datos['genero'],
        datos['duracion']
    )
    
    return jsonify({'calorias': calorias})

@app.route('/api/guardar-sesion', methods=['POST'])
def guardar_sesion_api():
    try:
        datos = request.json
        
        # Calcular calorías
        calorias = calcular_calorias(
            datos['bpm_promedio'],
            datos['edad'],
            datos['peso'],
            datos['genero'],
            datos['duracion']
        )
        datos['calorias'] = calorias
        
        # Guardar sesión
        guardar_sesion(datos)
        
        return jsonify({'success': True, 'calorias': calorias})
    except Exception as e:
        print(f"Error guardando sesión: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/historial')
def get_historial():
    try:
        historial = obtener_historial()
        return jsonify({'historial': historial})
    except Exception as e:
        print(f"Error obteniendo historial: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    t = threading.Thread(target=udp_server, daemon=True)
    t.start()
    print("Flask en http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)