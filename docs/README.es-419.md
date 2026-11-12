# Mumblebox 3D Asset Foundry

**Versión de Foundry 0.1.0-preview.25**

[English](../README.md) · [简体中文](README.zh-CN.md) · [Español (Latinoamérica)](README.es-419.md) · [Français](README.fr.md) · [Português (Brasil)](README.pt-BR.md)

**Crea imágenes y recursos 3D en tu equipo, por tu cuenta o con tu agente de programación.**

Foundry reúne flujos de trabajo de IA en asistentes que ofrecen ajustes útiles, vistas previas y resultados guardados. Puedes empezar sin conocer ComfyUI. El instalador de Pinokio configura el software y sus dependencias. Si necesitas más control, puedes acceder a los grafos de ComfyUI.

Explora objetos para videojuegos, partes de personajes, cabello, splats gaussianos y recursos para proyectos creativos o impresión 3D. Revisa cada resultado según el uso que le darás. La geometría generada puede requerir edición, retopología, ajustes o preparación para imprimir.

[Instalar con Pinokio](PINOKIO.md) · [Versiones disponibles](https://github.com/mumblebox-gpt/mumblebox-foundry/releases) · [Configurar un agente](AGENT-SETUP.md) · [Historial de cambios](../CHANGELOG.md)

## Empieza más rápido con tu agente de programación

Pídele a un agente que genere un recurso inicial con Foundry y sigue trabajando con él en Blender u otro editor 3D.

- **El MCP le da herramientas al agente.** Puede consultar flujos y ajustes, enviar tareas, seguir el progreso, revisar vistas previas y obtener las exportaciones a través de los mismos servicios que usa la interfaz.
- **La habilidad complementaria le ofrece orientación.** Ayuda al agente a elegir un flujo de trabajo, respetar las entradas y los límites de memoria, revisar resultados y llevar un recurso a la siguiente herramienta.
- **La generación se realiza en tu equipo.** El agente puede avanzar con otras tareas mientras Foundry procesa una solicitud. Puedes revisar el resultado en el asistente y retomar el mismo trabajo guardado.

El objetivo es reducir el modelado repetitivo y ahorrar tiempo y tokens del agente. El ahorro real depende del recurso, del flujo y del acabado que necesite. Consulta la [guía del MCP y de la habilidad complementaria](AGENT-SETUP.md). La habilidad evoluciona con proyectos reales y comentarios de la comunidad.

## Elige un flujo de trabajo

| Flujo de trabajo | Qué obtienes | Cuándo usarlo |
| --- | --- | --- |
| **Imagen única o texto** | Una imagen pasa por generación de geometría con Pixal3D, refinamiento con Hi3D, limpieza, texturizado con TRELLIS.2 y exportación de los resultados seleccionados. Si hace falta, puedes crear la imagen a partir de texto dentro del asistente. | Es la ruta más directa para crear una malla, con menos etapas y modelos. Prueba con una referencia clara en vista de tres cuartos. |
| **Vistas múltiples** | Genera y revisa cuatro vistas con modelos Qwen o FLUX compatibles. Luego reconstruye con Pixal3D y da el acabado con Hi3D y TRELLIS.2. | Los humanoides son un buen punto de partida. Los métodos para vehículos, objetos y criaturas siguen mejorando. |
| **Guiado en 3D** | Usa una malla auxiliar de Pixal3D, vistas medidas en Blender, estimaciones de MoGe 2 y guía de Qwen antes de reconstruir y dar el acabado. | Para objetos que requieren elegir y verificar las vistas de cámara. Necesita más procesamiento. |
| **Splat y sólido** | Un splat gaussiano de Idol, de Sperid Labs, junto con geometría complementaria limpia y refinamiento opcional con Hi3D. | Para combinar una apariencia detallada con geometría más ligera, con vistas orbitales y comparaciones de mallas. |
| **De órbita a malla** | Genera una órbita con H3, revisa las vistas alineadas, reconstruye con Pixal3D y termina con Hi3D y TRELLIS.2. | Para comprobar los ángulos y descartar fotogramas borrosos o deformados antes de generar la malla. |
| **Plato giratorio virtual** | Genera una órbita con H3 y reconstruye con Meshroom o COLMAP + OpenMVS. | Para probar fotogrametría a partir de una órbita generada y coherente. |
| **CCORE Texto** | Crea un objeto estilizado con un método procedural a partir de palabras. Incluye 12 ejemplos editables, mejora opcional de la descripción con Qwen local, vista 3D y exportación GLB. | Para herramientas, muebles y objetos individuales de videojuegos. |
| **CCORE Imagen + texto** | Usa una imagen y una descripción con el proyector visual y el flujo de generación de CCORE. Puedes crear una referencia dentro del asistente. | Para conservar o cambiar detalles de una foto, un boceto o un render. |
| **HairDeck** | Tarjetas de cabello, variantes, hojas de procesamiento, ajustes, materiales, cadenas elásticas opcionales, vista previa de movimiento y exportaciones GLB o VRM según la selección. | Para referencias claras de peinados. Usa HairDeck y la integración de ComfyUI de FengLairh. |
| **Garment Particles (experimental)** | Generación de prendas, edición compatible con el modelo, patrones de costura, preparación de mallas, simulación experimental de caída de tela en Blender y transferencia al personaje. | Para explorar diseños de ropa. El ajuste y la deformación requieren revisión y trabajo adicional. |
| **Crear imágenes** | Imágenes individuales o pares de frente y reverso, edición, LoRA compatibles y una galería guardada. | Para preparar una referencia para otro asistente o guardar la imagen. |

Cada flujo tiene su propio asistente y su propia sección del grafo. Las tarjetas marcadas **Próximamente** describen funciones futuras.

## Empieza a crear

1. Instala [Pinokio](https://pinokio.co/) y sigue la [guía de instalación de Foundry](PINOKIO.md) para agregar este repositorio.
2. Elige **Install**, luego **Start Foundry** y **Open Foundry**.
3. Abre **Imagen única o texto**. Carga o arrastra una imagen, usa tu cámara web, elige una imagen de la galería o créala a partir de una descripción.
4. Revisa las vistas previas y elige las salidas. **Rocket Mode** puede ejecutar las etapas pendientes que seleccionaste sin detenerse en revisiones opcionales.

Si ya tienes ComfyUI, sigue [INSTALL.md](../INSTALL.md) y abre Mumblebox 3D Asset Foundry.json. La instalación prepara el software. La primera vez que usas un flujo de trabajo, se preparan los pesos que faltan antes de procesar. Deja espacio en disco para los pesos, los archivos de trabajo y los resultados.

## Revisa y exporta

Las salidas dependen del flujo de trabajo. Los asistentes ofrecen opciones compatibles como GLB, FBX, OBJ, BLEND, STL, SPZ, texturas, vistas previas y paquetes ZIP. Las mallas detalladas y reducidas pueden incluir UV y mapas horneados.

**Las caras cuadrangulares editables son opcionales.** Imagen única y Vistas múltiples ofrecen QuadriFlow e Instant Meshes en la CPU, o CyberRemesher con NVIDIA CUDA. Sus controles avanzados y su ayuda están en el asistente. Los picos de uso de CPU durante QuadriFlow son normales y el procesamiento puede tardar. Si desactivas las caras cuadrangulares, aún obtienes recursos triangulados con texturas. Las vistas previas GLB usan triángulos. Los formatos de edición compatibles conservan las caras cuadrangulares.

Revisa la topología para deformaciones, la geometría para impresión y colisiones, y los materiales en el editor o motor de destino. HairDeck ofrece salidas distintas para el GLB estático y el VRM con huesos elásticos. Su vista previa de giro de cabeza muestra el movimiento del cabello. Garment Particles sigue en fase experimental, en especial el ajuste al personaje y la caída de la tela.

Los paquetes incluyen los archivos seleccionados, un README, medidas, sumas de verificación, información de procedencia y los avisos que correspondan. Los paquetes normales excluyen las imágenes de origen privadas, las instrucciones de texto y los archivos de trabajo. El historial conserva los resultados guardados para revisarlos o reanudar operaciones compatibles. En **Historial → Videos** puedes reproducir, descargar o eliminar los videos guardados por separado.

## Idioma y accesibilidad

Elige el idioma en el encabezado o en **Configuración**. Foundry actualiza el texto de la interfaz en el momento con catálogos locales. Conserva el texto que escribiste, las referencias, las vistas previas y las tareas en curso.

El idioma de la interfaz es independiente del idioma de generación. Foundry conserva tus instrucciones de texto y las del modelo. Consulta la guía del modelo seleccionado al elegir el idioma en que escribirás tu descripción.

El autor de CCORE recomienda escribir las descripciones de generación en inglés. Los ejemplos integrados siguen el idioma de la interfaz. Usa **Traducir al inglés** para traducir una descripción con el asistente local de Qwen. Revísala antes de generar. Elige Q4 para usar menos memoria de video o Q8 para mayor precisión numérica. Q4 es el punto de partida recomendado. La precisión de Q8 no garantiza una mejor traducción. El modelo elegido debe caber en la GPU. Si no cabe, Foundry conserva tu texto. La traducción conserva el diseño. **Mejorar descripción** es una opción creativa independiente.

Usa **Tema** para elegir una apariencia clara u oscura. **Fuente** ofrece el tamaño predeterminado, 112%, 125%, 150%, 175% y 200%. Los controles avanzados están disponibles cuando los necesites.

## Mantén Foundry y la habilidad al día

Las versiones nuevas pueden traer flujos de trabajo, correcciones y mejores instrucciones para el agente. Busca actualizaciones con regularidad, en especial si hace tiempo que no usas Foundry.

El encabezado muestra si hay una actualización disponible. En Pinokio, espera a que terminen las tareas activas y usa la opción normal **Update**. Si usas ComfyUI por separado, sigue [INSTALL.md](../INSTALL.md).

Al actualizar Foundry se actualiza la habilidad que incluye. **Si copiaste la habilidad al directorio de habilidades del agente, actualiza también esa copia.** La aplicación y la copia de la habilidad se actualizan por separado.

La habilidad complementaria indica al agente que consulte la versión y las funciones de la aplicación en ejecución, revise la información de compatibilidad y busque actualizaciones. El agente debe explicar en tu idioma cualquier incompatibilidad observada o actualización pendiente. La aplicación en ejecución indica qué controles están disponibles.

## Hardware, almacenamiento y condiciones de los modelos

Esta es una **versión preliminar para Windows y NVIDIA**. El equipo de referencia tiene una RTX 4080 SUPER con 16 GB de VRAM y 64 GB de RAM. Los requisitos varían según el flujo de trabajo. Esa configuración no representa un mínimo garantizado. CCORE revisa la memoria de la GPU y ofrece ajustes compatibles que requieren menos memoria si la combinación solicitada no cabe.

Desde Configuración puedes administrar los modelos instalados y revisar qué archivos se eliminarán al limpiar la caché. Si un flujo necesita un modelo publicado, lo prepara de nuevo. Revisa la lista de archivos antes de limpiar la caché o eliminar pesos.

El código original de Foundry tiene licencia **Apache-2.0**. Los modelos, los pesos y otras herramientas conservan sus propias condiciones. Lee [THIRD-PARTY.md](../THIRD-PARTY.md), especialmente antes de usar Foundry con fines comerciales.

## Un proyecto en comunidad

Foundry reúne y conecta aportes de investigadores, autores de modelos y creadores de flujos de trabajo. Gracias a las personas detrás de Pixal3D, TRELLIS.2, Hi3D, Idol, HairDeck, CCORE, Garment Particles, Qwen, FLUX, MoGe, ComfyUI, Blender y las integraciones de la comunidad.

La sección **Acerca de** incluye créditos de los modelos y agradecimientos a quienes contribuyen. Nos ayudan las sugerencias de flujos de trabajo, los informes de errores, las correcciones de traducción y las solicitudes de cambios. Ayúdanos a que más personas puedan usar flujos locales que les sirvan.

- [Informa un problema o sugiere un flujo de trabajo](https://github.com/mumblebox-gpt/mumblebox-foundry/issues)
- [Configura un agente](AGENT-SETUP.md)
- [Organización de la localización y guía de contribución](LOCALIZATION.md)
- [Dependencias y entornos de ejecución](../dependencies.json)
- [Evidencia de validación y límites](RELEASE-VALIDATION.md)
- [Más proyectos de Mumblebox](https://github.com/mumblebox-gpt?tab=repositories)

La **Hoja de ruta** de la aplicación enumera las funciones planeadas. Las versiones publicadas indican qué compilaciones puedes instalar.
