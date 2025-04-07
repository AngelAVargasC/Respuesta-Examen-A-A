core/                         # Carpeta raíz del proyecto (contiene manage.py)
├── core/                     # Configuración del proyecto (settings, urls, wsgi, etc.)
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── etl_app/                  # Aplicación que contiene la lógica ETL y el dashboard
│   ├── migrations/
│   ├── management/
│   │   └── commands/
│   │       └── process_etl.py   # Comando para ejecutar el proceso ETL
│   ├── models.py             # Modelos: Alarm, Outage, JoinedRecord
│   ├── templates/
│   │   └── etl_app/
│   │       └── dashboard.html  # Plantilla para el dashboard
│   ├── urls.py               # Rutas de la aplicación (dashboard, etc.)
│   └── views.py              # Vistas para mostrar el dashboard
├── Dockerfile                # Definición de la imagen Docker
├── docker-compose.yml        # Configuración de Docker Compose
└── requirements.txt          # Lista de dependencias Python


Requisitos
Docker y Docker Compose instalados en la máquina.

(Opcional) Python 3.9+ para ejecutar sin Docker (no recomendado para portabilidad).

Instrucciones de Ejecución
1. Clonar el Repositorio
Clona el repositorio o descarga el archivo ZIP y descomprímelo en una carpeta.

2. Construir y Levantar el Contenedor Docker
Abre una terminal en la raíz del proyecto (donde se encuentran el Dockerfile y el docker-compose.yml) y ejecuta:

docker-compose up --build

Esto construirá la imagen Docker y levantará el contenedor en el puerto 8000.

3. Ejecutar el Proceso ETL
El proceso ETL (descarga, procesamiento, carga en la base de datos y cálculo de respaldo) 
se implementa como un comando de management. Desde otra terminal (o en el mismo, abriendo otra ventana), ejecuta:

docker-compose run web python manage.py process_etl

Este comando:

Descargará automáticamente los archivos de Outlook (los adjuntos se guardarán en la carpeta de ejecución del contenedor).

Procesará y normalizará los datos de ambos archivos.

Cargará la información en la base de datos (usando los modelos de Django).

Realizará el JOIN y calculará el tiempo de respaldo.

Exportará la tabla resultante a un archivo CSV (resultados_joined.csv).

4. Acceder al Dashboard Web
Una vez que el contenedor esté en ejecución, abre tu navegador y accede a:

http://localhost:8000/dashboard