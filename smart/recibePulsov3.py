from flask import Flask, render_template, request, jsonify, redirect, url_for
import socket
import pandas as pd
from datetime import datetime, date
import time
import signal
import sys
import threading
import json
import webbrowser
from urllib.parse import quote

class ContadorPulsosCardiacos:
    def __init__(self, puerto_udp=3333, timeout=10, umbral=2000):
        self.puerto_udp = puerto_udp
        self.timeout = timeout
        self.umbral = umbral
        self.datos = []
        self.sock = None
        self.ejecutandose = True
        self.midiendo = False
        
        # Variables para detección de pulsos
        self.ultimo_valor = 0
        self.contador_pulsos = 0
        self.inicio_sesion = None
        
        # Datos del usuario
        self.usuario = {}
        
        # Estadísticas en tiempo real
        self.stats_tiempo_real = {
            'pulsos_totales': 0,
            'frecuencia_cardiaca': 0,
            'calorias_quemadas': 0,
            'zona_intensidad': 'Reposo',
            'tiempo_transcurrido': '00:00:00',
            'pulsos_por_minuto': 0,
            'color_zona': '#6B7280',
            'fc_maxima': 220,
            'porcentaje_fc_max': 0
        }
        
        # Configurar manejo de señales
        signal.signal(signal.SIGINT, self.manejar_cierre)
        signal.signal(signal.SIGTERM, self.manejar_cierre)
        
        # Iniciar servidor UDP
        self.iniciar_servidor_udp()
        
        # Iniciar hilo de escucha UDP
        self.hilo_udp = threading.Thread(target=self.escuchar_datos_udp, daemon=True)
        self.hilo_udp.start()
    
    def calcular_edad(self, fecha_nacimiento):
        """Calcula la edad a partir de la fecha de nacimiento"""
        try:
            nacimiento = datetime.strptime(fecha_nacimiento, '%Y-%m-%d').date()
            hoy = date.today()
            edad = hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
            return edad
        except:
            return 25  # Edad por defecto
    
    def calcular_fc_maxima(self, edad):
        """Calcula la frecuencia cardíaca máxima"""
        return 220 - edad
    
    def calcular_zonas_intensidad(self, fc_actual, fc_max):
        """Calcula la zona de intensidad cardíaca actual"""
        if fc_max <= 0:
            return "Sin datos", "#6B7280"
            
        porcentaje = (fc_actual / fc_max) * 100
        
        if porcentaje < 50:
            return "Reposo", "#6B7280"  # Gris
        elif porcentaje < 60:
            return "Calentamiento", "#3B82F6"  # Azul
        elif porcentaje < 70:
            return "Zona Grasa", "#10B981"  # Verde
        elif porcentaje < 80:
            return "Zona Aeróbica", "#F59E0B"  # Amarillo
        elif porcentaje < 90:
            return "Zona Anaeróbica", "#EF4444"  # Rojo
        else:
            return "Zona Máxima", "#7C2D12"  # Rojo oscuro
    
    def calcular_calorias(self, fc_promedio, tiempo_minutos, peso, edad, es_hombre=True):
        """Calcula las calorías quemadas basado en FC, peso, edad y género"""
        if tiempo_minutos <= 0:
            return 0
            
        if es_hombre:
            # Fórmula para hombres
            calorias = ((-55.0969 + (0.6309 * fc_promedio) + (0.1988 * peso) + (0.2017 * edad)) / 4.184) * 60 * (tiempo_minutos / 60)
        else:
            # Fórmula para mujeres  
            calorias = ((-20.4022 + (0.4472 * fc_promedio) - (0.1263 * peso) + (0.074 * edad)) / 4.184) * 60 * (tiempo_minutos / 60)
        
        return max(0, calorias)  # No puede ser negativo
    
    def detectar_pulso(self, valor_raw):
        """Detecta si hay un nuevo pulso basado en el valor analógico"""
        pulso_detectado = False
        
        if valor_raw > self.umbral and self.ultimo_valor <= self.umbral:
            self.contador_pulsos += 1
            pulso_detectado = True
            self.actualizar_estadisticas_tiempo_real()
        
        self.ultimo_valor = valor_raw
        return pulso_detectado
    
    def actualizar_estadisticas_tiempo_real(self):
        """Actualiza las estadísticas que se muestran en tiempo real"""
        if not self.midiendo or not self.inicio_sesion:
            return
        
        tiempo_transcurrido = (datetime.now() - self.inicio_sesion).total_seconds()
        minutos_transcurridos = tiempo_transcurrido / 60
        
        # Calcular FC actual (últimos 60 segundos)
        if minutos_transcurridos > 0:
            fc_actual = int(self.contador_pulsos / minutos_transcurridos)
        else:
            fc_actual = 0
        
        # Calcular datos del usuario
        edad = self.calcular_edad(self.usuario.get('fecha_nacimiento', '2000-01-01'))
        fc_max = self.calcular_fc_maxima(edad)
        zona, color_zona = self.calcular_zonas_intensidad(fc_actual, fc_max)
        
        # Calcular calorías
        peso = float(self.usuario.get('peso', 70))
        calorias = self.calcular_calorias(fc_actual, minutos_transcurridos, peso, edad)
        
        # Formatear tiempo
        horas = int(tiempo_transcurrido // 3600)
        minutos = int((tiempo_transcurrido % 3600) // 60)
        segundos = int(tiempo_transcurrido % 60)
        tiempo_formato = f"{horas:02d}:{minutos:02d}:{segundos:02d}"
        
        self.stats_tiempo_real = {
            'pulsos_totales': self.contador_pulsos,
            'frecuencia_cardiaca': fc_actual,
            'calorias_quemadas': round(calorias, 1),
            'zona_intensidad': zona,
            'color_zona': color_zona,
            'tiempo_transcurrido': tiempo_formato,
            'pulsos_por_minuto': fc_actual,
            'fc_maxima': fc_max,
            'porcentaje_fc_max': round((fc_actual / fc_max) * 100, 1) if fc_max > 0 else 0
        }
    
    def es_valor_analogico_valido(self, valor):
        """Verifica si el valor recibido es un valor analógico válido"""
        try:
            val_int = int(valor)
            return 0 <= val_int <= 4095
        except ValueError:
            return False
    
    def iniciar_servidor_udp(self):
        """Inicia el servidor UDP para recibir datos del ESP32"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(("", self.puerto_udp))
            self.sock.settimeout(1)  # Timeout corto para no bloquear
            print(f"✅ Servidor UDP iniciado en puerto {self.puerto_udp}")
        except Exception as e:
            print(f"❌ Error al iniciar servidor UDP: {e}")
    
    def escuchar_datos_udp(self):
        """Escucha los datos del sensor en un hilo separado"""
        print("🎧 Iniciando escucha UDP...")
        while self.ejecutandose:
            if not self.midiendo:
                time.sleep(0.1)
                continue
                
            try:
                data, addr = self.sock.recvfrom(64)
                valor_str = data.decode().strip()
                
                if self.es_valor_analogico_valido(valor_str):
                    valor_raw = int(valor_str)
                    timestamp = datetime.now()
                    
                    pulso_detectado = self.detectar_pulso(valor_raw)
                    
                    if pulso_detectado:
                        registro = {
                            'timestamp': timestamp,
                            'numero_pulso': self.contador_pulsos,
                            'valor_raw_sensor': valor_raw,
                            'tiempo_desde_inicio': (timestamp - self.inicio_sesion).total_seconds()
                        }
                        self.datos.append(registro)
                        print(f"💓 Pulso {self.contador_pulsos}: {valor_raw} - FC: {self.stats_tiempo_real['frecuencia_cardiaca']} BPM")
                        
            except socket.timeout:
                continue  # Continúa el loop
            except Exception as e:
                if self.ejecutandose:
                    print(f"⚠️ Error en UDP: {e}")
                continue
    
    def iniciar_medicion(self):
        """Inicia una nueva sesión de medición"""
        self.datos = []
        self.contador_pulsos = 0
        self.ultimo_valor = 0
        self.inicio_sesion = datetime.now()
        self.midiendo = True
        print("🚀 ¡Medición iniciada!")
        return True
    
    def detener_medicion(self):
        """Detiene la medición actual"""
        self.midiendo = False
        print("⏹️ Medición detenida")
        return self.guardar_excel()
    
    def guardar_excel(self):
        """Guarda los datos en Excel y retorna el nombre del archivo"""
        if not self.datos:
            print("⚠️ No hay datos para guardar")
            return None
        
        try:
            df = pd.DataFrame(self.datos)
            timestamp_archivo = datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre_usuario = self.usuario.get('nombre', 'usuario').replace(' ', '_')
            nombre_archivo = f"sesion_cardiaca_{nombre_usuario}_{timestamp_archivo}.xlsx"
            
            # Calcular estadísticas finales
            stats = self.calcular_estadisticas_finales(df)
            
            with pd.ExcelWriter(nombre_archivo, engine='openpyxl') as writer:
                # Datos de pulsos
                df.to_excel(writer, sheet_name='Pulsos_Detectados', index=False)
                
                # Datos del usuario
                usuario_df = pd.DataFrame([
                    ['=== DATOS DEL USUARIO ===', ''],
                    ['Nombre Completo', f"{self.usuario.get('nombre', '')} {self.usuario.get('apellido', '')}"],
                    ['Edad', f"{stats.get('edad', 'N/A')} años"],
                    ['Peso', f"{self.usuario.get('peso', 'N/A')} kg"],
                    ['Altura', f"{self.usuario.get('altura', 'N/A')} cm"],
                    ['Fecha de Nacimiento', self.usuario.get('fecha_nacimiento', 'N/A')],
                    ['', ''],
                    ['=== ESTADÍSTICAS DE LA SESIÓN ===', ''],
                ] + [[k, v] for k, v in stats.items()], columns=['Parámetro', 'Valor'])
                
                usuario_df.to_excel(writer, sheet_name='Resumen_Sesion', index=False)
            
            print(f"💾 Archivo guardado: {nombre_archivo}")
            return nombre_archivo
            
        except Exception as e:
            print(f"❌ Error al guardar Excel: {e}")
            return None
    
    def calcular_estadisticas_finales(self, df):
        """Calcula estadísticas finales de la sesión"""
        if len(df) == 0:
            return {}
        
        duracion_min = (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 60
        fc_promedio = len(df) / duracion_min if duracion_min > 0 else 0
        
        edad = self.calcular_edad(self.usuario.get('fecha_nacimiento', '2000-01-01'))
        fc_max = self.calcular_fc_maxima(edad)
        peso = float(self.usuario.get('peso', 70))
        
        calorias_totales = self.calcular_calorias(fc_promedio, duracion_min, peso, edad)
        zona_promedio, _ = self.calcular_zonas_intensidad(fc_promedio, fc_max)
        
        return {
            'edad': edad,
            'fc_maxima_teorica': fc_max,
            'duracion_minutos': round(duracion_min, 2),
            'total_pulsos': len(df),
            'fc_promedio': round(fc_promedio, 1),
            'zona_intensidad_promedio': zona_promedio,
            'calorias_quemadas': round(calorias_totales, 1),
            'porcentaje_fc_max_promedio': round((fc_promedio / fc_max) * 100, 1),
            'fecha_sesion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def manejar_cierre(self, signum, frame):
        """Maneja el cierre limpio del programa"""
        print("\n🔄 Cerrando aplicación...")
        self.ejecutandose = False
        if self.midiendo:
            self.detener_medicion()
        if self.sock:
            self.sock.close()
        sys.exit(0)

# Crear instancia global del contador
contador = ContadorPulsosCardiacos()

# Crear aplicación Flask
app = Flask(__name__)
app.secret_key = 'monitor_cardiaco_2025'

@app.route('/')
def index():
    """Página principal - Registro de usuario"""
    return render_template('registro_usuario.html')

@app.route('/sesion')
def sesion():
    """Página de sesión de medición"""
    if not contador.usuario:
        return redirect(url_for('index'))
    return render_template('sesion_medicion.html')

@app.route('/guardar_usuario', methods=['POST'])
def guardar_usuario():
    """Guarda los datos del usuario"""
    try:
        data = request.get_json()
        
        # Validar datos básicos
        required_fields = ['nombre', 'apellido', 'edad', 'peso', 'altura', 'fecha_nacimiento']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'success': False, 'error': f'Campo {field} requerido'})
        
        # Guardar datos del usuario
        contador.usuario = {
            'nombre': data['nombre'].strip(),
            'apellido': data['apellido'].strip(),
            'edad': int(data['edad']),
            'peso': float(data['peso']),
            'altura': int(data['altura']),
            'fecha_nacimiento': data['fecha_nacimiento']
        }
        
        print(f"👤 Usuario registrado: {contador.usuario['nombre']} {contador.usuario['apellido']}")
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Error al guardar usuario: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/iniciar_medicion', methods=['POST'])
def iniciar_medicion():
    """Inicia la medición de pulsos"""
    try:
        if contador.iniciar_medicion():
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'No se pudo iniciar la medición'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/detener_medicion', methods=['POST'])
def detener_medicion():
    """Detiene la medición de pulsos"""
    try:
        archivo = contador.detener_medicion()
        return jsonify({
            'success': True, 
            'archivo': archivo if archivo else 'No se guardaron datos'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stats')
def api_stats():
    """API para obtener estadísticas en tiempo real"""
    return jsonify(contador.stats_tiempo_real)

@app.route('/api/usuario')
def api_usuario():
    """API para obtener datos del usuario"""
    return jsonify(contador.usuario)

if __name__ == '__main__':
    print("=" * 60)
    print("🫀 MONITOR CARDÍACO - SISTEMA INICIADO")
    print("=" * 60)
    print(f"🌐 Servidor web: http://localhost:5000")
    print(f"📡 Puerto UDP: {contador.puerto_udp}")
    print(f"🎯 Umbral de pulso: {contador.umbral}")
    print("=" * 60)
    
    # Abrir navegador automáticamente
    threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5000')).start()
    
    # Iniciar aplicación Flask
    app.run(debug=False, host='0.0.0.0', port=5000)
