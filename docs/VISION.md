# Lector de Resumenes Bancarios — Vision del Producto

## Que problema resuelve

Los contadores argentinos reciben cada mes extractos bancarios en PDF de sus clientes. Para cumplir con las obligaciones fiscales (especialmente el **Impuesto a los Debitos y Creditos, Ley 25.413**), deben:

1. Abrir el PDF del extracto (que puede tener 70+ paginas).
2. Leer movimiento por movimiento (pueden ser 1900+ por extracto).
3. Clasificar cada uno como debito o credito.
4. Agruparlos por tipo (impuestos, comisiones, transferencias, compras, etc.).
5. Totalizar por mes y verificar que cuadre con los totales del banco.
6. Armar el reporte para presentar ante ARCA (ex AFIP).

Este trabajo es **manual, repetitivo y propenso a errores**. Un solo extracto puede llevar horas. Multiplicado por varios clientes y varios bancos, es una carga operativa enorme.

**Este programa automatiza todo ese flujo**: sube el PDF, parsea los movimientos, los clasifica, valida los saldos al centavo, y genera el reporte listo para ARCA.

---

## MVP (Estado actual)

El MVP esta funcional y cubre el caso de uso principal:

| Funcionalidad | Estado |
|---|---|
| Subir PDF de extracto Banco Supervielle | Implementado |
| Parsear movimientos automaticamente (regex + pdfplumber) | Implementado |
| Inferir signo (debito/credito) por variacion de saldo | Implementado |
| Validar saldos al centavo (1915 movimientos, 0 errores) | Implementado |
| Clasificar movimientos por tipo (31 reglas, 99.95% precision) | Implementado |
| Capturar lineas de detalle adicional del PDF | Implementado |
| Persistencia en base de datos (SQLAlchemy + SQLite) | Implementado |
| Interfaz web basica (FastAPI + Jinja2 + HTMX) | Implementado |
| Suite de tests (99 tests en verde) | Implementado |

### Condiciones para que funcione

- El PDF debe ser un **extracto de cuenta corriente del Banco Supervielle**.
- El PDF debe ser **texto seleccionable** (no una imagen escaneada).
- El formato del extracto debe seguir la estructura tabular estandar de Supervielle (fecha, concepto, monto, saldo).
- Python 3.11+ instalado.

---

## Funcionalidades extra a implementar

### Corto plazo (alto impacto, baja complejidad)

1. **Modulo de reportes para ARCA**
   - Generar reporte mensual con totales de debitos y creditos.
   - Separar Impuesto Ley 25.413 sobre debitos vs sobre creditos.
   - Calcular impuesto neto (descontando devoluciones).
   - Exportar a XLSX para que la contadora lo adjunte a la presentacion.

2. **Reporte de conciliacion bancaria**
   - Comparar saldo inicial + movimientos = saldo final por mes.
   - Marcar discrepancias automaticamente.

3. **Dashboard de resumen**
   - Visualizar en la web los totales mensuales, graficos de debitos/creditos.
   - Filtrar movimientos por tipo, fecha, monto.

### Mediano plazo (escalabilidad)

4. **Soporte multi-banco**
   - Santander, Galicia, BBVA, Macro, Banco Nacion.
   - La arquitectura ya usa Strategy Pattern: cada banco implementa la interfaz `ParserBanco`.
   - Deteccion automatica del banco segun el PDF (Factory Pattern).

5. **Soporte multi-cliente**
   - Gestionar varios clientes (empresas) desde la misma interfaz.
   - Cada cliente con su historial de extractos y reportes.

6. **Deteccion de duplicados**
   - Evitar que se cargue el mismo extracto dos veces.
   - Detectar movimientos duplicados entre periodos solapados.

7. **Soporte multi-formato**
   - Aceptar CSV y XLSX ademas de PDF.
   - Algunos bancos (Galicia) exportan directo desde HomeBanking en estos formatos.

### Largo plazo (valor agregado)

8. **Generacion automatica de asientos contables**
   - Mapear tipos de movimiento a cuentas del plan contable.
   - Exportar asientos listos para importar en sistemas contables (Tango, Colppy, etc.).

9. **Alertas y anomalias**
   - Detectar movimientos inusuales (montos fuera de rango, tipos nuevos).
   - Notificar a la contadora para revision manual.

10. **API para integraciones**
    - Exponer endpoints REST para que otros sistemas consuman los datos parseados.
    - Integracion con sistemas de gestion contable.

11. **OCR para PDFs escaneados**
    - Procesar extractos que son imagenes (fotos o escaneos) usando OCR.
    - Amplia la compatibilidad a extractos mas viejos o de bancos con PDFs no-texto.

---

## Como escala el proyecto

```
Hoy                          Futuro
─────────────────────────────────────────────────
1 banco (Supervielle)    -->  6+ bancos argentinos
1 formato (PDF)          -->  PDF + CSV + XLSX
1 reporte (Ley 25.413)  -->  Conciliacion + asientos contables
1 usuario local          -->  Multi-cliente con login
SQLite (dev)             -->  PostgreSQL (produccion)
```

### Arquitectura preparada para crecer

- **Strategy Pattern**: agregar un banco nuevo = crear un archivo `app/parsers/nuevo_banco.py` que implemente la interfaz comun. No se toca codigo existente.
- **Pydantic v2**: el modelo de dominio `MovimientoBancario` es agnostico al banco. Todos los parsers producen el mismo modelo.
- **Repository Pattern**: la capa de persistencia esta separada de la logica. Migrar de SQLite a PostgreSQL es cambiar una linea de configuracion.
- **FastAPI**: el backend ya expone una API REST, agregar endpoints nuevos es trivial.

---

## Resumen en una linea

> Transforma PDFs de extractos bancarios en reportes fiscales listos para ARCA, ahorrando horas de trabajo manual a contadores argentinos.
