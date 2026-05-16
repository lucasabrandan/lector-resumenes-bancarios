# 📚 Documentación del proyecto

Esta carpeta contiene la documentación **conceptual** del proyecto: el "por qué" detrás de cada decisión. La documentación técnica del código vive en los docstrings y en `app/` directamente.

## Estructura

```
docs/
├── README.md          ← Este archivo
├── adr/               ← Architecture Decision Records (decisiones técnicas)
│   ├── README.md
│   ├── 0001-modelo-dominio.md
│   ├── 0002-decimal-para-dinero.md
│   └── ...
├── bitacora.md        ← Diario de desarrollo (aprendizajes, dudas, errores)
├── dominio.md         ← Glosario del dominio bancario y contable argentino
└── images/            ← Diagramas y capturas
```

## ¿Qué es cada cosa?

### ADRs (`adr/`)

Un **Architecture Decision Record** es un documento corto que registra una decisión técnica importante. Cada decisión que tomamos durante el proyecto y que no es obvia se documenta en un ADR.

Formato estándar:
- **Contexto**: ¿qué problema enfrentamos?
- **Decisión**: ¿qué elegimos?
- **Alternativas consideradas**: ¿qué otras opciones había?
- **Consecuencias**: ¿qué implica esta decisión?

Los ADRs son **inmutables**: si una decisión cambia, creás un ADR nuevo que "supersede" al anterior. Eso te da un historial completo del pensamiento del proyecto.

### Bitácora (`bitacora.md`)

Diario informal de desarrollo. Acá anotás:
- Errores raros que encontraste y cómo los resolviste.
- Cosas que probaste y no funcionaron.
- Insights del dominio (ej: "descubrí que Supervielle imprime IDENTIFICACIÓN en una línea aparte").
- Recursos útiles que consultaste.

Es informal y cronológico, no requiere formato estricto.

### Glosario (`dominio.md`)

Diccionario de términos del negocio. Cuando un programador entra al proyecto por primera vez, no sabe qué es un "DEBIN", qué significa "Imp. Ley 25413", o qué es "CBU". Acá se aclara.

## Filosofía

> "La mejor documentación es la que se escribe MIENTRAS se decide, no después."

No esperés a terminar para documentar. Cada vez que tomes una decisión no obvia, abrí el ADR correspondiente y dejá escrito el porqué. Tu yo del futuro te lo va a agradecer.
