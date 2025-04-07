import os
import re
import pandas as pd
import logging
import matplotlib.pyplot as plt
import sqlite3
import datetime
import pythoncom
import win32com.client
import tkinter as tk
from tkinter import filedialog

# Configuración básica del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

def update_log(message):
    logging.info(message)

###############################################
# Funciones para descarga automatizada de correos
###############################################
def download_email_attachments():
    """
    Descarga los adjuntos de los correos en Outlook cuyo asunto contenga:
      "Reporte de alarmas"
    Solo descarga correos recibidos hoy.
    Los archivos se guardan en la carpeta de ejecución actual.
    """
    update_log("=== Iniciando descarga de correos (Hoy) ===")
    pythoncom.CoInitialize()
    try:
        # Usar la carpeta actual
        download_folder = os.getcwd()
        update_log(f"Carpeta de descarga: {download_folder}")
        
        try:
            outlook_app = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook_app.GetNamespace("MAPI")
            update_log("Outlook inicializado para descarga de correos.")
        except Exception as e:
            update_log(f"Error al inicializar Outlook: {e}")
            return

        # Acceder a la bandeja de entrada (Inbox)
        inbox = namespace.GetDefaultFolder(6)  # 6 es Inbox
        messages = inbox.Items
        messages.Sort("[ReceivedTime]", True)
        today_date = datetime.date.today()
        downloaded_count = 0

        for msg in messages:
            try:
                subject = msg.Subject
            except Exception:
                continue  # Saltar si no se obtiene el asunto

            # Filtrar por asunto deseado
            if "Reporte de alarmas" in subject:
                try:
                    received = msg.ReceivedTime
                    received_date = received.date()
                except Exception as e:
                    update_log(f"Error al obtener fecha del correo: {e}")
                    continue

                # Procesar solo correos de hoy
                if received_date != today_date:
                    continue

                attachments = msg.Attachments
                if attachments.Count > 0:
                    for i in range(1, attachments.Count + 1):
                        try:
                            attachment = attachments.Item(i)
                            save_path = os.path.join(download_folder, attachment.FileName)
                            attachment.SaveAsFile(save_path)
                            update_log(f"Adjunto descargado: {save_path}")
                            downloaded_count += 1
                        except Exception as e:
                            update_log(f"Error al descargar adjunto: {e}")
                else:
                    update_log("No se encontraron adjuntos en el correo con asunto deseado.")
        update_log(f"Descarga completada, {downloaded_count} adjuntos descargados.")
    finally:
        pythoncom.CoUninitialize()

###############################################
# Funciones de normalización y parseo
###############################################
def normalize_string(s):
    """
    Normaliza una cadena:
      - Elimina espacios al inicio y final.
      - Convierte a mayúsculas.
      - Elimina caracteres especiales (dejando solo letras, números y espacios).
      - Unifica múltiples espacios en uno.
    """
    if not isinstance(s, str):
        return s
    s = s.strip().upper()
    s = re.sub(r'[^A-Z0-9 ]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s

def parse_site_name(site_str):
    """
    Extrae el identificador del sitio a partir de cadenas con formatos variables.
    
    Ejemplos:
      "NODEB NAME=TAMREY1591, LOGICRNCID=141"   -> "TAMREY1591"
      "NODEB NAMETAMREY1591 LOGICRNCID141"        -> "TAMREY1591"
      "YUCYAX0519"                               -> "YUCYAX0519"
    """
    if not isinstance(site_str, str):
        return site_str
    s = site_str.strip().upper()
    m = re.search(r'NODEB\s*NAME[=]?\s*([A-Z0-9]+)', s)
    if m:
        return m.group(1).strip()
    m = re.search(r'NAME[=]?\s*([A-Z0-9]+)', s)
    if m:
        return m.group(1).strip()
    s = re.sub(r'[^A-Z0-9]', '', s)
    return s

###############################################
# ETL: Procesamiento de archivos
###############################################
def etl_alarms(alarms_file):
    """
    Lee el archivo de alarmas (Excel con 4 pestañas), normaliza los datos y los une en un solo DataFrame.
    Se espera que cada hoja tenga las columnas:
      "Occurred On (NT)" o "Last Occurred (NT)", "Cleared On (NT)", "Alarm Source", "Name"
    Se agrega la columna 'region' con el nombre de la pestaña y se extrae el identificador del sitio.
    """
    try:
        sheets_dict = pd.read_excel(alarms_file, sheet_name=None)
    except Exception as e:
        update_log(f"Error al leer el archivo de alarmas: {e}")
        return None

    frames = []
    # Para la mayoría se espera "Occurred On (NT)", pero en la pestaña PENINSULA puede venir "Last Occurred (NT)"
    for sheet_name, df_tab in sheets_dict.items():
        # Si es la pestaña PENINSULA, se renombra "Last Occurred (NT)" a "Occurred On (NT)" si existe
        if sheet_name.upper() == "PENINSULA":
            if "Last Occurred (NT)" in df_tab.columns:
                df_tab.rename(columns={"Last Occurred (NT)": "Occurred On (NT)"}, inplace=True)
        
        # Verificar que la hoja tenga las columnas esperadas
        expected_columns = ['Occurred On (NT)', 'Cleared On (NT)', 'Alarm Source', 'Name']
        if not all(col in df_tab.columns for col in expected_columns):
            update_log(f"La hoja '{sheet_name}' no contiene todas las columnas esperadas. Se omitirá.")
            continue
        
        df_tab['region'] = sheet_name
        df_tab.rename(columns={
            'Occurred On (NT)': 'alarm_occurred_on',
            'Cleared On (NT)': 'alarm_cleared_on',
            'Alarm Source': 'alarm_source',
            'Name': 'alarm_name'
        }, inplace=True)
        df_tab['alarm_occurred_on'] = pd.to_datetime(df_tab['alarm_occurred_on'], dayfirst=True, errors='coerce')
        df_tab['alarm_cleared_on'] = pd.to_datetime(df_tab['alarm_cleared_on'], dayfirst=True, errors='coerce')
        for col in ['alarm_source', 'alarm_name', 'region']:
            df_tab[col] = df_tab[col].astype(str).apply(normalize_string)
        frames.append(df_tab)
    
    if not frames:
        update_log("Ninguna hoja contenía las columnas esperadas en el archivo de alarmas.")
        return None
    df_alarms = pd.concat(frames, ignore_index=True)
    df_alarms['site_parsed_alarm'] = df_alarms['alarm_source'].apply(parse_site_name)
    update_log(f"Archivo de alarmas procesado con {len(df_alarms)} registros.")
    return df_alarms

def etl_outages(outages_file):
    """
    Lee el archivo de outages (CSV o Excel), normaliza los datos y retorna un DataFrame.
    Se esperan las columnas:
      "Occurred On (NT)", "Cleared On (NT)", "MO Name", "Name"
    Se extrae el identificador del sitio.
    """
    try:
        if outages_file.lower().endswith('.csv'):
            df_outages = pd.read_csv(outages_file)
        else:
            df_outages = pd.read_excel(outages_file)
    except Exception as e:
        update_log(f"Error al leer el archivo de outages: {e}")
        return None

    df_outages.rename(columns={
        'Occurred On (NT)': 'outage_occurred_on',
        'Cleared On (NT)': 'outage_cleared_on',
        'MO Name': 'mo_name',
        'Name': 'outage_name'
    }, inplace=True)
    df_outages['outage_occurred_on'] = pd.to_datetime(df_outages['outage_occurred_on'], dayfirst=True, errors='coerce')
    df_outages['outage_cleared_on'] = pd.to_datetime(df_outages['outage_cleared_on'], dayfirst=True, errors='coerce')
    for col in ['mo_name', 'outage_name']:
        df_outages[col] = df_outages[col].astype(str).apply(normalize_string)
    df_outages['site_parsed_outage'] = df_outages['mo_name'].apply(parse_site_name)
    update_log(f"Archivo de outages procesado con {len(df_outages)} registros.")
    return df_outages

###############################################
# Funciones para cargar en SQLite
###############################################
def load_table(df, db_file, table_name):
    """
    Carga el DataFrame en la base de datos SQLite.
    Se elimina la tabla si existe para asegurar el nuevo esquema.
    """
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        conn.commit()
        
        if table_name == "alarms":
            create_table_sql = f"""
            CREATE TABLE {table_name} (
                alarm_occurred_on TEXT,
                alarm_cleared_on TEXT,
                alarm_source TEXT,
                alarm_name TEXT,
                region TEXT,
                site_parsed_alarm TEXT
            );
            """
        elif table_name == "outages":
            create_table_sql = f"""
            CREATE TABLE {table_name} (
                outage_occurred_on TEXT,
                outage_cleared_on TEXT,
                mo_name TEXT,
                outage_name TEXT,
                site_parsed_outage TEXT
            );
            """
        elif table_name == "alarms_outages_joined":
            create_table_sql = f"""
            CREATE TABLE {table_name} (
                alarm_occurred_on TEXT,
                alarm_cleared_on TEXT,
                alarm_source TEXT,
                alarm_name TEXT,
                region TEXT,
                site_parsed_alarm TEXT,
                outage_occurred_on TEXT,
                outage_cleared_on TEXT,
                mo_name TEXT,
                outage_name TEXT,
                site_parsed_outage TEXT,
                battery_backup_time TEXT,
                backup_minutes REAL
            );
            """
        else:
            update_log("Nombre de tabla no reconocido.")
            return False

        cursor.execute(create_table_sql)
        conn.commit()

        if table_name == "alarms":
            insert_sql = f"""
            INSERT INTO {table_name} (
                alarm_occurred_on, alarm_cleared_on, alarm_source, alarm_name, region, site_parsed_alarm
            ) VALUES (?, ?, ?, ?, ?, ?);
            """
            for index, row in df.iterrows():
                cursor.execute(insert_sql, (
                    row['alarm_occurred_on'].strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(row['alarm_occurred_on']) else None,
                    row['alarm_cleared_on'].strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(row['alarm_cleared_on']) else None,
                    row['alarm_source'],
                    row['alarm_name'],
                    row['region'],
                    row['site_parsed_alarm']
                ))
        elif table_name == "outages":
            insert_sql = f"""
            INSERT INTO {table_name} (
                outage_occurred_on, outage_cleared_on, mo_name, outage_name, site_parsed_outage
            ) VALUES (?, ?, ?, ?, ?);
            """
            for index, row in df.iterrows():
                cursor.execute(insert_sql, (
                    row['outage_occurred_on'].strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(row['outage_occurred_on']) else None,
                    row['outage_cleared_on'].strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(row['outage_cleared_on']) else None,
                    row['mo_name'],
                    row['outage_name'],
                    row['site_parsed_outage']
                ))
        elif table_name == "alarms_outages_joined":
            insert_sql = f"""
            INSERT INTO {table_name} (
                alarm_occurred_on, alarm_cleared_on, alarm_source, alarm_name, region, site_parsed_alarm,
                outage_occurred_on, outage_cleared_on, mo_name, outage_name, site_parsed_outage,
                battery_backup_time, backup_minutes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            for index, row in df.iterrows():
                cursor.execute(insert_sql, (
                    row['alarm_occurred_on'].strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(row['alarm_occurred_on']) else None,
                    row['alarm_cleared_on'].strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(row['alarm_cleared_on']) else None,
                    row['alarm_source'],
                    row['alarm_name'],
                    row['region'],
                    row['site_parsed_alarm'],
                    row['outage_occurred_on'].strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(row['outage_occurred_on']) else None,
                    row['outage_cleared_on'].strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(row['outage_cleared_on']) else None,
                    row['mo_name'],
                    row['outage_name'],
                    row['site_parsed_outage'],
                    str(row['battery_backup_time']) if pd.notnull(row['battery_backup_time']) else None,
                    row['backup_minutes']
                ))
        conn.commit()
        update_log(f"Datos cargados exitosamente en la tabla '{table_name}' en la base de datos '{db_file}'.")
        conn.close()
        return True
    except Exception as e:
        update_log(f"Error al cargar datos en la base de datos: {e}")
        return False

###############################################
# JOIN entre alarmas y outages
###############################################
def join_alarms_outages(df_alarms, df_outages):
    """
    Realiza el JOIN entre los DataFrames de alarmas y outages para obtener registros donde:
      - La alarma tenga el nombre "MINOR RECT FAILURE" (en alarm_name)
      - Se unan usando los identificadores parseados de sitio.
      - Se filtre que outage_occurred_on >= alarm_occurred_on.
    Retorna el DataFrame resultante con el cálculo del tiempo de respaldo.
    """
    df_minor = df_alarms[df_alarms['alarm_name'].str.contains("MINOR RECT FAILURE", case=False, na=False)]
    update_log(f"Filtradas {len(df_minor)} alarmas de tipo 'MINOR RECT FAILURE'.")
    
    df_merged = pd.merge(df_minor, df_outages, left_on='site_parsed_alarm', right_on='site_parsed_outage', how='inner')
    update_log(f"Unión de alarmas y outages resultó en {len(df_merged)} registros.")
    
    df_merged = df_merged[df_merged['outage_occurred_on'] >= df_merged['alarm_occurred_on']]
    update_log(f"Tras filtrar por tiempos válidos, quedan {len(df_merged)} registros.")
    
    df_merged['battery_backup_time'] = df_merged['outage_occurred_on'] - df_merged['alarm_occurred_on']
    df_merged['backup_minutes'] = df_merged['battery_backup_time'].dt.total_seconds() / 60.0
    return df_merged

###############################################
# Exportar la tabla resultante a CSV
###############################################
def export_joined_to_csv(db_file="etl_alarms.db", table_name="alarms_outages_joined", output_csv="resultados_joined.csv"):
    """
    Recupera los datos de la tabla de unión en SQLite y los exporta a un archivo CSV.
    """
    try:
        conn = sqlite3.connect(db_file)
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql_query(query, conn)
        conn.close()
        df.to_csv(output_csv, index=False)
        update_log(f"Datos exportados exitosamente a {output_csv}.")
    except Exception as e:
        update_log(f"Error al exportar datos a CSV: {e}")

###############################################
# Generación de gráfica a partir del JOIN
###############################################
def generate_graph_from_joined(db_file="etl_alarms.db", table_name="alarms_outages_joined"):
    """
    Recupera los datos de la tabla de unión y genera una gráfica de barras que muestra 
    el tiempo promedio de respaldo (en minutos) por sitio.
    """
    try:
        conn = sqlite3.connect(db_file)
        query = f"SELECT * FROM {table_name}"
        df_db = pd.read_sql_query(query, conn)
        update_log(f"Datos recuperados de la tabla '{table_name}'.")
        conn.close()
    except Exception as e:
        update_log(f"Error al recuperar datos de la tabla de unión: {e}")
        return

    df_db['site_id'] = df_db['site_parsed_alarm']
    df_grouped = df_db.groupby('site_id', as_index=False)['backup_minutes'].mean()

    plt.figure(figsize=(10, 6))
    plt.bar(df_grouped['site_id'], df_grouped['backup_minutes'], color='skyblue')
    plt.xlabel('ID del Sitio')
    plt.ylabel('Tiempo Promedio de Respaldo (minutos)')
    plt.title('Tiempo Promedio de Respaldo de Batería por Sitio')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.show()

###############################################
# Programa Principal
###############################################
if __name__ == '__main__':
    # Paso 0: Descargar automáticamente los archivos desde Outlook
    download_email_attachments()
    
    # Rutas de archivos de entrada (se asume que se descargaron en la carpeta actual)
    alarms_file = "LOGS DE AE SEMANA 01-2025.xlsx"   # Archivo Excel con 4 pestañas
    outages_file = "nodeb_unavailable_2025 01.csv"     # Archivo CSV de outages

    # Procesar y normalizar los datos de cada archivo
    df_alarms = etl_alarms(alarms_file)
    df_outages = etl_outages(outages_file)

    # Cargar cada DataFrame en su respectiva tabla en SQLite
    if df_alarms is not None:
        update_log(f"Archivo de alarmas procesado: {len(df_alarms)} registros.")
        load_table(df_alarms, db_file="etl_alarms.db", table_name="alarms") 
    else:
        update_log("Error en el procesamiento del archivo de alarmas.")

    if df_outages is not None:
        update_log(f"Archivo de outages procesado: {len(df_outages)} registros.")
        load_table(df_outages, db_file="etl_alarms.db", table_name="outages")
    else:
        update_log("Error en el procesamiento del archivo de outages.")

    # Realizar el JOIN para obtener tiempos de respaldo para alarmas "MINOR RECT FAILURE"
    if df_alarms is not None and df_outages is not None:
        df_joined = join_alarms_outages(df_alarms, df_outages)
        update_log(f"Registros finales en la unión: {len(df_joined)}")
        if load_table(df_joined, db_file="etl_alarms.db", table_name="alarms_outages_joined"):
            generate_graph_from_joined(db_file="etl_alarms.db", table_name="alarms_outages_joined")
            # Exportar los datos de la tabla resultante a CSV
            export_joined_to_csv(db_file="etl_alarms.db", table_name="alarms_outages_joined", output_csv="resultados_joined.csv")
    else:
        update_log("No se pudo realizar el JOIN de datos.")
