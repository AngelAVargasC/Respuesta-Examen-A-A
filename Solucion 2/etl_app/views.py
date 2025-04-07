from django.shortcuts import render
from django.db.models import Avg ,Count
from etl_app.models import JoinedRecord
from etl_app.models import Alarm, JoinedRecord
from collections import defaultdict

def dashboard(request):
    # Obtener los datos agrupados por sitio y calcular el promedio
    data = (
        JoinedRecord.objects
        .values('site_parsed_alarm')
        .annotate(avg_backup=Avg('backup_minutes'))
        .order_by('site_parsed_alarm')
    )
    labels = [d['site_parsed_alarm'] for d in data]
    values = [d['avg_backup'] for d in data]
    
    context = {
        'labels': labels,
        'values': values,
    }
    return render(request, 'dashboard.html', context)


def dashboard_mas(request):
    """
    Prepara los datos para el dashboard avanzado con tres gráficas:

    1) Gráfico 1: Top 20 tipos de alarma (Eje X: tipo de alarma, Eje Y: conteo total de registros).
    2) Gráfico 2: Total de sitios (site_parsed_alarm) que presentan "MINOR RECT FAILURE".
    3) Gráfico 3: Por cada región, determina cuál es la alarma más frecuente (falla top) y muestra su conteo.
    """

    # --- Gráfico 1: Top 20 tipos de alarma ---
    try:
        alarm_type_data = (
            Alarm.objects
            .values('alarm_name')
            .annotate(total=Count('id'))
            .order_by('-total')[:20]
        )
    except Exception as e:
        print("Error en consulta Gráfico 1:", e)
        alarm_type_data = []

    graph1_labels = [record['alarm_name'] for record in alarm_type_data]
    graph1_counts = [record['total'] for record in alarm_type_data]

    # --- Gráfico 2: Total de sitios con "MINOR RECT FAILURE" ---
    try:
        minor_site_count = (
            Alarm.objects
            .filter(alarm_name__icontains="MINOR RECT FAILURE")
            .values('site_parsed_alarm')
            .distinct()
            .count()
        )
    except Exception as e:
        print("Error en consulta Gráfico 2:", e)
        minor_site_count = 0

    # --- Gráfico 3: Falla más común por región ---
    try:
        region_alarm_data = (
            Alarm.objects
            .values('region', 'alarm_name')
            .annotate(count=Count('id'))
        )
    except Exception as e:
        print("Error en consulta Gráfico 3:", e)
        region_alarm_data = []

    # Agrupar por región, y obtener la alarma con mayor count
    region_top = defaultdict(lambda: {'alarm_name': '', 'count': 0})
    for record in region_alarm_data:
        reg = record['region']
        alarm = record['alarm_name']
        count = record['count']
        if count > region_top[reg]['count']:
            region_top[reg] = {'alarm_name': alarm, 'count': count}

    # Extraer para frontend
    region_labels = list(region_top.keys())
    region_top_counts = [region_top[reg]['count'] for reg in region_labels]
    region_top_alarm = [region_top[reg]['alarm_name'] for reg in region_labels]

    print("Regiones:", region_labels)
    print("Fallas top:", region_top_alarm)
    print("Conteos:", region_top_counts)

    context = {
        # Gráfico 1 y 2...
        'graph1_labels': graph1_labels,
        'graph1_counts': graph1_counts,
        'minor_site_count': minor_site_count,
        # Gráfico 3:
        'region_labels': region_labels,
        'region_top_counts': region_top_counts,
        'region_top_alarm': region_top_alarm,
    }
    return render(request, 'dashboard_mas.html', context)
