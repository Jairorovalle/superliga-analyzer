SUPERLIGA ANALYZER
===================

Qué hace
--------
Este programa entra a:
https://www.futbolgol.com/superliga/

y trata de extraer automáticamente la tabla de clasificación. Genera:
- superliga_datos.xlsx
- posición
- partidos jugados
- victorias/empates/derrotas
- goles a favor/en contra
- diferencia de goles
- puntos (si la página no los publica, los calcula como PG*3 + PE)
- métricas por partido

Cómo usarlo en un computador
----------------------------
1. Instala Python 3.11 o superior desde https://www.python.org/
2. Abre Terminal / PowerShell.
3. Instala las librerías:
   pip install pandas requests lxml openpyxl
4. Pon superliga_analyzer.py en una carpeta.
5. Desde esa carpeta ejecuta:
   python superliga_analyzer.py
6. Se creará superliga_datos.xlsx.

Importante
----------
La página puede cambiar su estructura o bloquear solicitudes automáticas. El programa usa
un navegador móvil como User-Agent para intentar evitar bloqueos básicos, pero no garantiza
acceso si FutbolGol exige JavaScript, cookies, login o protección anti-bot.

Siguiente evolución
-------------------
Podemos convertir esto en una herramienta más completa que:
- lea calendario y resultados;
- identifique automáticamente tu equipo;
- actualice la tabla después de cada jornada;
- calcule rachas;
- compare rivales;
- proyecte puntos finales;
- calcule escenarios de clasificación;
- genere un dashboard.