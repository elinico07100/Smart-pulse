import socket
import threading
from flask import Flask, render_template, jsonify
from datetime import datetime

app = Flask(__name__)

# Variables globales para almacenar los datos
bpm_data = {
    'bpm': 0,
    'timestamp': None,
    'client_addr': None
}

# Configuración UDP
HOST = '0.0.0.0'
PORT = 8888

def udp_server():
    """Servidor UDP que recibe datos del ESP32"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))
    print(f"Servidor UDP escuchando en {HOST}:{PORT}")
    
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            bpm = data.decode('utf-8').strip()
            
            # Actualizar datos globales
            bpm_data['bpm'] = bpm
            bpm_data['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            bpm_data['client_addr'] = str(addr)
            
            print(f"BPM recibido de {addr}: {bpm}")
            
        except Exception as e:
            print(f"Error en servidor UDP: {e}")

@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')

@app.route('/api/bpm')
def get_bpm():
    """API endpoint para obtener datos BPM actuales"""
    return jsonify(bpm_data)

if __name__ == '__main__':
    # Iniciar servidor UDP en un hilo separado
    udp_thread = threading.Thread(target=udp_server, daemon=True)
    udp_thread.start()
    
    # Iniciar servidor Flask
    print("Iniciando servidor Flask en http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)