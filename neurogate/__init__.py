"""NeuroGate: capa de seguridad para datos neuronales (prototipo educativo).

Este paquete contiene los ocho módulos del sistema. La visión completa, los
contratos entre módulos y el roadmap de 11 pasos están en SPEC.md (raíz).

No importamos los submódulos aquí a propósito: algunos dependen de librerías
externas (numpy, scikit-learn...) y queremos que `import neurogate` funcione
incluso antes de instalar requirements.txt.
"""

__version__ = "0.1.0"  # Paso 1 de 11: cimientos
