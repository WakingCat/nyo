#!/bin/bash
# Script para aplicar migración de Base de Datos
# Ejecutar: bash migrations/apply_migration.sh

echo "=== Aplicando Migración: Actualizar Estados de Solicitudes ==="
echo ""
echo "Por favor ingresa la contraseña de MySQL cuando se solicite..."
echo ""

mysql -u root -p hive_mining_db << 'EOF'
ALTER TABLE solicitudes_traslado 
MODIFY COLUMN estado ENUM(
    'pendiente_lab', 
    'pendiente_coordinador', 
    'pendiente', 
    'aprobado', 
    'rechazado', 
    'rechazado_lab', 
    'ejecutado'
) DEFAULT 'pendiente_lab';

SELECT 'Migración completada exitosamente!' AS STATUS;
DESCRIBE solicitudes_traslado;
EOF

echo ""
echo "=== Migración Finalizada ==="
echo "Ahora puedes reiniciar el servidor Flask."
