import os
import re
import datetime
import pythoncom
import win32com.client
import pandas as pd
from django.core.management.base import BaseCommand
from django.utils import timezone
from etl_app.models import Alarm, Outage, JoinedRecord
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

def update_log(message):
    logging.info(message)

###############################################
# Funciones para descarga automatizada de correos
###############################################
def download_email_attachments():
    update_log("=== Iniciando descarga de correos (Hoy) ===")
    pythoncom.CoInitialize()
    try:
        download_folder = os.getcwd()
        update_log(f"Carpeta de descarga: {download_folder}")
        try:
            outlook_app = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook_app.GetNamespace("MAPI")
            update_log("Outlook inicializado para descarga de correos.")
        except Exception as e:
            update_log(f"Error al inicializar Outlook: {e}")
            return

        inbox = namespace.GetDefaultFolder(6)  # 6 es Inbox
        messages = inbox.Items
        messages.Sort("[ReceivedTime]", True)
        today_date = datetime.date.today()
        downloaded_count = 0

        for msg in messages:
            try:
                subject = msg.Subject
            except Exception:
                continue

            if "Reporte de alarmas" in subject:
                try:
                    received = msg.ReceivedTime
                    received_date = received.date()
                except Exception as e:
                    update_log(f"Error al obtener fecha del correo: {e}")
                    continue

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
    if not isinstance(s, str):
        return s
    s = s.strip().upper()
    s = re.sub(r'[^A-Z0-9 ]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s

def parse_site_name(site_str):
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
# Función para hacer aware los datetimes si son naive
###############################################
def make_aware_if_naive(dt):
    if dt is not None and timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt

###############################################
# ETL: Procesamiento de archivos
###############################################
def etl_alarms(alarms_file):
    try:
        sheets_dict = pd.read_excel(alarms_file, sheet_name=None)
    except Exception as e:
        update_log(f"Error al leer el archivo de alarmas: {e}")
        return None

    frames = []
    for sheet_name, df_tab in sheets_dict.items():
        # Para la pestaña PENINSULA, si existe "Last Occurred (NT)", renombrarlo a "Occurred On (NT)"
        if sheet_name.upper() == "PENINSULA":
            if "Last Occurred (NT)" in df_tab.columns:
                df_tab.rename(columns={"Last Occurred (NT)": "Occurred On (NT)"}, inplace=True)
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

def join_alarms_outages(df_alarms, df_outages):
    df_minor = df_alarms[df_alarms['alarm_name'].str.contains("MINOR RECT FAILURE", case=False, na=False)]
    update_log(f"Filtradas {len(df_minor)} alarmas de tipo 'MINOR RECT FAILURE'.")
    df_merged = pd.merge(df_minor, df_outages, left_on='site_parsed_alarm', right_on='site_parsed_outage', how='inner')
    update_log(f"JOIN resultante: {len(df_merged)} registros.")
    df_merged = df_merged[df_merged['outage_occurred_on'] >= df_merged['alarm_occurred_on']]
    update_log(f"Después de filtrar por tiempos válidos, quedan {len(df_merged)} registros.")
    df_merged['battery_backup_time'] = df_merged['outage_occurred_on'] - df_merged['alarm_occurred_on']
    df_merged['backup_minutes'] = df_merged['battery_backup_time'].dt.total_seconds() / 60.0
    return df_merged

class Command(BaseCommand):
    help = "Ejecuta la descarga de correos, el proceso ETL y almacena los datos en la base de datos"

    def handle(self, *args, **options):
        update_log("=== Iniciando proceso ETL ===")
        # Descargar archivos de Outlook
        download_email_attachments()

        # Archivos de entrada (en la carpeta actual)
        alarms_file = "LOGS DE AE SEMANA 01-2025.xlsx"
        outages_file = "nodeb_unavailable_2025 01.csv"

        df_alarms = etl_alarms(alarms_file)
        df_outages = etl_outages(outages_file)
        if df_alarms is None or df_outages is None:
            self.stdout.write(self.style.ERROR("Error en el procesamiento de archivos."))
            return

        # Eliminar datos previos
        Alarm.objects.all().delete()
        Outage.objects.all().delete()
        JoinedRecord.objects.all().delete()

        # Guardar Alarmas (convertir datetimes a aware)
        for _, row in df_alarms.iterrows():
            Alarm.objects.create(
                alarm_occurred_on = make_aware_if_naive(row['alarm_occurred_on']),
                alarm_cleared_on = make_aware_if_naive(row['alarm_cleared_on']),
                alarm_source = row['alarm_source'],
                alarm_name = row['alarm_name'],
                region = row['region'],
                site_parsed_alarm = row['site_parsed_alarm']
            )
        
        # Guardar Outages
        for _, row in df_outages.iterrows():
            Outage.objects.create(
                outage_occurred_on = make_aware_if_naive(row['outage_occurred_on']),
                outage_cleared_on = make_aware_if_naive(row['outage_cleared_on']),
                mo_name = row['mo_name'],
                outage_name = row['outage_name'],
                site_parsed_outage = row['site_parsed_outage']
            )
        
        # Realizar JOIN y guardar registros en JoinedRecord
        df_joined = join_alarms_outages(df_alarms, df_outages)
        update_log(f"Registros finales en el JOIN: {len(df_joined)}")
        if df_joined is not None:
            for _, row in df_joined.iterrows():
                JoinedRecord.objects.create(
                    alarm_occurred_on = make_aware_if_naive(row['alarm_occurred_on']),
                    alarm_cleared_on = make_aware_if_naive(row['alarm_cleared_on']),
                    alarm_source = row['alarm_source'],
                    alarm_name = row['alarm_name'],
                    region = row['region'],
                    site_parsed_alarm = row['site_parsed_alarm'],
                    outage_occurred_on = make_aware_if_naive(row['outage_occurred_on']),
                    outage_cleared_on = make_aware_if_naive(row['outage_cleared_on']),
                    mo_name = row['mo_name'],
                    outage_name = row['outage_name'],
                    site_parsed_outage = row['site_parsed_outage'],
                    battery_backup_time = str(row['battery_backup_time']),
                    backup_minutes = row['backup_minutes']
                )
        self.stdout.write(self.style.SUCCESS("Proceso ETL completado y datos almacenados en la Base de Datos."))
        self.stdout.write(self.style.SUCCESS("Accede al dashboard en http://localhost:8000/"))

# Helper para convertir datetimes naive a aware
def make_aware_if_naive(dt):
    import pandas as pd
    from django.utils import timezone
    if dt is None or pd.isnull(dt):
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt