import socket
import pandas as pd
from datetime import datetime
import time
import signal
import sys

class ContadorPulsos:
    def __init__(self, puerto=3333, timeout=10, umbral=2000):
        self.puerto = puerto
        self.timeout = timeout
        self.umbral = umbral  # Umbral para detectar pulsos
        self.datos = []
        self.sock = None
        self.ejecutandose = True
        
        # Variables para detección de pulsos
        self.ultimo_valor = 0
        self.contador_pulsos = 0
        self.valores_raw = []  # Para mostrar valores raw en consola
        
        # Configurar manejo de señales para cierre limpio
        signal.signal(signal.SIGINT, self.manejar_cierre)
        signal.signal(signal.SIGTERM, self.manejar_cierre)
    
    def iniciar_servidor(self):
        """Inicia el servidor UDP"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(("", self.puerto))
            self.sock.settimeout(self.timeout)
            print(f"Escuchando datos del sensor HW-827 en puerto {self.puerto}...")
            print(f"Umbral de detección de pulsos: {self.umbral}")
            print(f"Timeout configurado a {self.timeout} segundos")
            print("Presiona Ctrl+C para detener y guardar los datos\n")
        except Exception as e:
            print(f"Error al iniciar servidor: {e}")
            sys.exit(1)
    
    def detectar_pulso(self, valor_raw):
        """Detecta si hay un nuevo pulso basado en el valor analógico"""
        pulso_detectado = False
        
        # Detectar flanco ascendente: valor actual > umbral Y valor anterior <= umbral
        if valor_raw > self.umbral and self.ultimo_valor <= self.umbral:
            self.contador_pulsos += 1
            pulso_detectado = True
        
        self.ultimo_valor = valor_raw
        return pulso_detectado
    
    def es_valor_analogico_valido(self, valor):
        """Verifica si el valor recibido es un valor analógico válido (0-4095)"""
        try:
            val_int = int(valor)
            return 0 <= val_int <= 4095  # Rango del ADC del ESP32
        except ValueError:
            return False
    
    def escuchar_datos(self):
        """Escucha los datos del sensor y detecta pulsos"""
        ultimo_dato = time.time()
        print("Formato: [Timestamp] | IP → Valor_Raw (Pulsos_Totales) [PULSO!]")
        print("-" * 60)
        
        while self.ejecutandose:
            try:
                data, addr = self.sock.recvfrom(64)
                valor_str = data.decode().strip()
                timestamp = datetime.now()
                
                # Solo procesar valores analógicos válidos
                if self.es_valor_analogico_valido(valor_str):
                    valor_raw = int(valor_str)
                    
                    # Detectar si hay un nuevo pulso
                    pulso_detectado = self.detectar_pulso(valor_raw)
                    
                    # Mostrar en consola con indicador de pulso
                    pulso_indicador = " [PULSO!]" if pulso_detectado else ""
                    print(f"{timestamp.strftime('%H:%M:%S')} | {addr[0]} → {valor_raw} ({self.contador_pulsos}){pulso_indicador}")
                    
                    # Guardar solo cuando se detecta un pulso
                    if pulso_detectado:
                        registro = {
                            'timestamp': timestamp,
                            'numero_pulso': self.contador_pulsos,
                            'valor_raw_sensor': valor_raw,
                            'tiempo_desde_inicio': (timestamp - self.datos[0]['timestamp']).total_seconds() if self.datos else 0
                        }
                        self.datos.append(registro)
                    
                else:
                    print(f"{timestamp.strftime('%H:%M:%S')} | {addr[0]} → {valor_str} (dato no válido)")
                
                ultimo_dato = time.time()
                
            except socket.timeout:
                tiempo_sin_datos = time.time() - ultimo_dato
                if tiempo_sin_datos > self.timeout:
                    print(f"\nNo se recibieron datos por {self.timeout} segundos.")
                    print("Detectada posible desconexión del sensor.")
                    break
            except Exception as e:
                print(f"Error al recibir datos: {e}")
                break
    
    def calcular_estadisticas_pulsos(self, df):
        """Calcula estadísticas avanzadas de los pulsos"""
        if len(df) < 2:
            return {}
        
        # Calcular intervalos entre pulsos
        df_sorted = df.sort_values('timestamp')
        intervalos = []
        
        for i in range(1, len(df_sorted)):
            intervalo = (df_sorted.iloc[i]['timestamp'] - df_sorted.iloc[i-1]['timestamp']).total_seconds()
            intervalos.append(intervalo)
        
        # Estadísticas básicas
        duracion_total_min = (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 60
        duracion_total_seg = (df['timestamp'].max() - df['timestamp'].min()).total_seconds()
        
        estadisticas = {
            'total_pulsos': len(df),
            'duracion_total_minutos': duracion_total_min,
            'duracion_total_segundos': duracion_total_seg,
            'frecuencia_promedio_ppm': len(df) / duracion_total_min if duracion_total_min > 0 else 0,
            'frecuencia_promedio_pps': len(df) / duracion_total_seg if duracion_total_seg > 0 else 0,
            'intervalo_promedio_segundos': sum(intervalos) / len(intervalos) if intervalos else 0,
            'intervalo_minimo_segundos': min(intervalos) if intervalos else 0,
            'intervalo_maximo_segundos': max(intervalos) if intervalos else 0,
        }
        
        # Análisis por ventanas de tiempo (cada minuto)
        estadisticas.update(self.calcular_frecuencia_por_minuto(df_sorted))
        
        return estadisticas
    
    def calcular_frecuencia_por_minuto(self, df_sorted):
        """Calcula frecuencia de pulsos por cada minuto de medición"""
        if len(df_sorted) < 2:
            return {}
        
        inicio = df_sorted['timestamp'].min()
        fin = df_sorted['timestamp'].max()
        duracion_total = (fin - inicio).total_seconds()
        minutos_totales = int(duracion_total // 60) + 1
        
        pulsos_por_minuto = []
        
        for minuto in range(minutos_totales):
            inicio_ventana = inicio + pd.Timedelta(minutes=minuto)
            fin_ventana = inicio + pd.Timedelta(minutes=minuto+1)
            
            pulsos_en_ventana = df_sorted[
                (df_sorted['timestamp'] >= inicio_ventana) & 
                (df_sorted['timestamp'] < fin_ventana)
            ]
            
            pulsos_por_minuto.append(len(pulsos_en_ventana))
        
        # Filtrar minutos con 0 pulsos para promedios más representativos
        pulsos_activos = [p for p in pulsos_por_minuto if p > 0]
        
        return {
            'frecuencia_maxima_ppm': max(pulsos_por_minuto) if pulsos_por_minuto else 0,
            'frecuencia_minima_ppm': min([p for p in pulsos_por_minuto if p > 0]) if pulsos_activos else 0,
            'minutos_con_actividad': len(pulsos_activos),
            'minutos_sin_actividad': len([p for p in pulsos_por_minuto if p == 0]),
            'promedio_pulsos_minutos_activos': sum(pulsos_activos) / len(pulsos_activos) if pulsos_activos else 0
        }
    
    def guardar_excel(self):
        """Guarda los datos de pulsos en un archivo Excel"""
        if not self.datos:
            print("No se detectaron pulsos para guardar.")
            return
        
        try:
            # Crear DataFrame
            df = pd.DataFrame(self.datos)
            
            # Generar nombre de archivo con timestamp
            timestamp_archivo = datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre_archivo = f"pulsos_contador_{timestamp_archivo}.xlsx"
            
            # Crear un writer para múltiples hojas
            with pd.ExcelWriter(nombre_archivo, engine='openpyxl') as writer:
                # Hoja principal con datos de pulsos
                df.to_excel(writer, sheet_name='Pulsos_Detectados', index=False)
                
                # Calcular estadísticas
                stats = self.calcular_estadisticas_pulsos(df)
                
                # Crear hoja de estadísticas
                if stats:
                    stats_df = pd.DataFrame([
                        ['=== ESTADÍSTICAS GENERALES ===', ''],
                        ['Total de Pulsos Detectados', stats['total_pulsos']],
                        ['Duración Total (minutos)', f"{stats['duracion_total_minutos']:.2f}"],
                        ['Duración Total (segundos)', f"{stats['duracion_total_segundos']:.1f}"],
                        ['', ''],
                        ['=== FRECUENCIAS ===', ''],
                        ['Frecuencia Promedio (pulsos/minuto)', f"{stats['frecuencia_promedio_ppm']:.2f}"],
                        ['Frecuencia Promedio (pulsos/segundo)', f"{stats['frecuencia_promedio_pps']:.3f}"],
                        ['Frecuencia Máxima por Minuto', f"{stats['frecuencia_maxima_ppm']}"],
                        ['Frecuencia Mínima por Minuto (activos)', f"{stats['frecuencia_minima_ppm']}"],
                        ['Promedio en Minutos Activos', f"{stats['promedio_pulsos_minutos_activos']:.2f}"],
                        ['', ''],
                        ['=== INTERVALOS ENTRE PULSOS ===', ''],
                        ['Intervalo Promedio (segundos)', f"{stats['intervalo_promedio_segundos']:.3f}"],
                        ['Intervalo Mínimo (segundos)', f"{stats['intervalo_minimo_segundos']:.3f}"],
                        ['Intervalo Máximo (segundos)', f"{stats['intervalo_maximo_segundos']:.3f}"],
                        ['', ''],
                        ['=== ANÁLISIS TEMPORAL ===', ''],
                        ['Minutos con Actividad', stats['minutos_con_actividad']],
                        ['Minutos sin Actividad', stats['minutos_sin_actividad']],
                        ['', ''],
                        ['=== CONFIGURACIÓN USADA ===', ''],
                        ['Umbral de Detección', self.umbral],
                        ['Archivo Generado', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
                    ], columns=['Parámetro', 'Valor'])
                    
                    stats_df.to_excel(writer, sheet_name='Estadisticas', index=False)
            
            print(f"\n✓ Datos guardados exitosamente en: {nombre_archivo}")
            print(f"✓ Total de pulsos detectados y guardados: {len(self.datos)}")
            
            # Mostrar estadísticas en consola
            if stats:
                print(f"✓ Duración total: {stats['duracion_total_minutos']:.2f} minutos")
                print(f"✓ Frecuencia promedio: {stats['frecuencia_promedio_ppm']:.2f} pulsos/minuto")
                print(f"✓ Intervalo promedio entre pulsos: {stats['intervalo_promedio_segundos']:.3f} segundos")
                print(f"✓ Total de valores raw procesados: {self.contador_pulsos} (incluyendo no-pulsos)")
                
        except Exception as e:
            print(f"Error al guardar archivo Excel: {e}")
            # Intentar guardar como CSV como respaldo
            try:
                nombre_csv = f"pulsos_contador_{timestamp_archivo}.csv"
                df.to_csv(nombre_csv, index=False)
                print(f"✓ Datos guardados como respaldo en CSV: {nombre_csv}")
            except Exception as e2:
                print(f"Error también al guardar CSV: {e2}")
    
    def manejar_cierre(self, signum, frame):
        """Maneja el cierre limpio del programa"""
        print(f"\n\nRecibida señal de cierre ({signum}). Cerrando programa...")
        self.ejecutandose = False
        if self.sock:
            self.sock.close()
        self.guardar_excel()
        print("Programa finalizado.")
        sys.exit(0)
    
    def ejecutar(self):
        """Ejecuta el contador de pulsos"""
        try:
            self.iniciar_servidor()
            self.escuchar_datos()
        finally:
            if self.sock:
                self.sock.close()
            self.guardar_excel()

# Configuración y ejecución
if __name__ == "__main__":
    # Configuración del sistema
    PUERTO_UDP = 3333           # Puerto donde escucha
    TIMEOUT_SEGUNDOS = 10       # Segundos sin datos para considerar desconexión
    UMBRAL_PULSO = 2000         # Valor analógico para detectar pulso (ajustar según sensor)
    
    print("=== CONTADOR DE PULSOS HW-827 ===")
    print(f"Configuración:")
    print(f"- Puerto UDP: {PUERTO_UDP}")
    print(f"- Timeout: {TIMEOUT_SEGUNDOS}s")
    print(f"- Umbral de pulso: {UMBRAL_PULSO}")
    print(f"- Rango esperado del sensor: 0-4095")
    print()
    
    contador = ContadorPulsos(
        puerto=PUERTO_UDP, 
        timeout=TIMEOUT_SEGUNDOS,
        umbral=UMBRAL_PULSO
    )
    
    try:
        contador.ejecutar()
    except KeyboardInterrupt:
        print("\n\nPrograma interrumpido por el usuario.")
    except Exception as e:
        print(f"Error inesperado: {e}")
    finally:
        print("Finalizando programa...")