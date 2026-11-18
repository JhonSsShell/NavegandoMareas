# Diagramas UML (diagramas como código)

Los diagramas están escritos en **PlantUML** y versionados junto al código, de modo que
evolucionan con él. `_estilo.iuml` y `_colores.iuml` centralizan la paleta: en los diagramas
de clases **el color de fondo identifica el patrón de diseño** de cada clase.

| Archivo | Diagrama |
|---|---|
| `01_componentes.puml` | Componentes por capas |
| `02a_clases_estrategias.puml` | Clases: Strategy, Template Method, Factory, Proxy, Facade |
| `02b_clases_eventos.puml` | Clases: Observer, Command, Iterator, dominio |
| `03_secuencia_ruta.puml` | Secuencia: cálculo de ruta (HIT/MISS de caché) |
| `04_secuencia_reruteo.puml` | Secuencia: cierre de calle y re-ruteo |
| `05_actividad_navegacion.puml` | Actividad: flujo de navegación |
| `06_estados_ruta.puml` | Estados: ciclo de vida de la ruta activa |
| `07_despliegue.puml` | Despliegue en Railway/Render |

Regenerar: `java -jar plantuml.jar -tpng *.puml` (o la extensión PlantUML de VS Code).
