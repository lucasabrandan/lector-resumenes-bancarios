# 📖 Glosario de dominio

Diccionario de términos bancarios y contables argentinos usados en el proyecto. Si sos programador y no entendés un término del código o de un ticket, buscalo acá.

---

## Términos contables / impositivos

### ARCA (ex AFIP)
**Agencia de Recaudación y Control Aduanero**. Organismo que en 2024 reemplazó a AFIP en Argentina. Es el equivalente al IRS (EE.UU.) o SAT (México). A esta agencia se presentan las declaraciones impositivas.

### Impuesto Ley 25.413 — Impuesto a los Débitos y Créditos Bancarios
Conocido como **"Impuesto al cheque"**. Es un tributo que grava cada débito y cada crédito en cuentas bancarias argentinas. La alícuota general es **0,6%** sobre cada movimiento.

**Por qué es importante en este proyecto:** la contadora necesita totalizar los débitos y créditos del mes para verificar que el banco haya retenido correctamente, y presentarlo a ARCA. **Este es el output principal del sistema.**

En los extractos aparece como:
- `Impuesto Débitos y Créditos/DB` (retención sobre un débito)
- `Impuesto Débitos y Créditos/CR` (retención sobre un crédito)

### Percepción de IVA RG 3337
Régimen por el cual el banco actúa como agente de percepción de IVA. Cobra un porcentaje adicional que después el contribuyente computa a favor en su declaración de IVA.

### Responsable Inscripto
Categoría tributaria de IVA. Las empresas que facturan más de cierto monto deben estar inscriptas como Responsable Inscripto y emiten facturas A.

### CUIT
**Clave Única de Identificación Tributaria**. Identificador fiscal de empresas y personas en Argentina. Tiene 11 dígitos. Equivalente al EIN (EE.UU.) o RFC (México).

---

## Términos bancarios

### CBU
**Clave Bancaria Uniforme**. Identificador único de una cuenta bancaria argentina. Tiene 22 dígitos. Se usa para transferencias.

### CVU
**Clave Virtual Uniforme**. Equivalente al CBU pero para cuentas de billeteras virtuales (Mercado Pago, Ualá, etc.). También 22 dígitos.

### DEBIN
**Débito Inmediato**. Mecanismo de pago donde el receptor solicita un débito a la cuenta del pagador, y este lo autoriza. Más usado entre empresas.

En extractos aparece como: `Debito DEBIN` (cuando te debitan) o como crédito (cuando te acreditan tras una solicitud aprobada).

### Visa Débito
Tarjeta de débito con marca Visa. Las compras se descuentan directamente de la cuenta corriente. **No confundir con Visa Crédito** (que difiere el pago).

En el extracto aparece como: `Compra Visa Débito` seguido del comercio.

### Pago Cheque de Cámara Recibida
Cuando vos depositás un cheque, el banco se lo envía a la cámara compensadora, y cuando el banco emisor confirma fondos, te lo acreditan. "De cámara recibida" = recibido desde la cámara.

### Cheque Rechazado Dep. de 48 hs
Cheque que depositaste, te lo acreditaron preventivamente, y al pasar el plazo de cámara (48hs hábiles) el banco emisor lo rechazó (por sin fondos, firma, etc.) y te lo descuentan.

### Cheque de Pago Diferido (CPD)
Cheque con fecha futura. Hasta esa fecha no se puede cobrar. Distinto del **cheque común** (a la vista).

### Saldo del período anterior
Saldo de la cuenta al cierre del período inmediato anterior. Es el "punto de partida" de un nuevo extracto.

### Sobregiro / Descubierto
Cuando la cuenta queda en saldo negativo. El banco cobra **intereses de sobregiro** (`Intereses de Sobregiro` en el extracto) por dejar plata "prestada".

### Comisión Permanencia saldo DR
Cargo que cobra el banco diariamente cuando la cuenta está en sobregiro (saldo negativo).

### Acreditación Cheque Dep. 48 Hs.
Cheque que depositaste y que se acredita 48 horas hábiles después (plazo de cámara compensadora).

### Pago Automático de Préstamo
Cuota de préstamo que el banco descuenta automáticamente cada mes de la cuenta.

---

## Términos técnicos del extracto Supervielle

### Hoja "Table N" (en el Excel intermedio)
Cada página del PDF original se convierte en una hoja del Excel cuando se usa una herramienta como **Tabula** para extraer tablas. Por eso un PDF de 70 páginas genera "Table 1" a "Table 70".

### Subtotal
Línea que aparece al pie de cada página del PDF, representando el saldo al final de esa página. Sirve como punto de control: el saldo del último movimiento de la página debe coincidir con el subtotal.

### Operación N° XXXXXXX
Identificador interno del banco para cada movimiento. Útil para auditoría, pero no es único globalmente (puede repetirse entre bancos distintos).

---

## Bancos argentinos relevantes (futuras integraciones)

| Banco | Particularidades del extracto |
|---|---|
| **Supervielle** | PDF tabular limpio. Conceptos en una línea, detalles adicionales en líneas subsiguientes. |
| **Santander** | PDF tabular. Estructura similar a Supervielle pero con más columnas. |
| **Galicia** | Exporta CSV/XLSX directamente desde HomeBanking. Más fácil de parsear. |
| **BBVA** | PDF complejo con múltiples secciones (cuenta + tarjetas en el mismo doc). |
| **Macro** | PDF con encoding particular, requiere atención al `pdfplumber`. |
| **Banco Nación** | PDF tabular con columnas anchas, descripciones largas que se cortan. |

---

## Recursos de referencia

- **AFIP/ARCA**: https://www.afip.gob.ar/
- **BCRA (Banco Central)**: https://www.bcra.gob.ar/
- **Ley 25.413** (texto oficial): https://servicios.infoleg.gob.ar/infolegInternet/anexos/65000-69999/66345/norma.htm
