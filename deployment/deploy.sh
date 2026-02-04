#!/bin/bash

# ============================================
# Script de Deployment - N&O Mining System
# ============================================

set -e  # Salir si hay error

echo "🚀 Iniciando deployment..."

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================
# 1. VERIFICAR REQUISITOS
# ============================================

echo -e "${YELLOW}📋 Verificando requisitos...${NC}"

# Verificar que estamos en el directorio correcto
if [ ! -f "run.py" ]; then
    echo -e "${RED}❌ Error: Ejecuta este script desde el directorio raíz del proyecto${NC}"
    exit 1
fi

# Verificar que existe .env
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ Error: Archivo .env no encontrado${NC}"
    echo "   Copia .env.example a .env y configúralo"
    exit 1
fi

# Verificar Redis
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}❌ Error: Redis no está corriendo${NC}"
    echo "   Ejecuta: sudo systemctl start redis-server"
    exit 1
else
    echo -e "${GREEN}✅ Redis activo${NC}"
fi

# Verificar MySQL
if ! mysql -e "SELECT 1" > /dev/null 2>&1; then
    echo -e "${RED}❌ Error: No se puede conectar a MySQL${NC}"
    exit 1
else
    echo -e "${GREEN}✅ MySQL activo${NC}"
fi

# ============================================
# 2. BACKUP DE BASE DE DATOS
# ============================================

echo -e "${YELLOW}💾 Creando backup de base de datos...${NC}"

BACKUP_FILE="backup_bd_$(date +%Y%m%d_%H%M%S).sql"
mysqldump -u root -p hive_mining_db > "$BACKUP_FILE"

if [ -f "$BACKUP_FILE" ]; then
    echo -e "${GREEN}✅ Backup creado: $BACKUP_FILE${NC}"
else
    echo -e "${RED}❌ Error creando backup${NC}"
    exit 1
fi

# ============================================
# 3. ACTIVAR ENTORNO VIRTUAL
# ============================================

echo -e "${YELLOW}🐍 Activando entorno virtual...${NC}"

if [ ! -d "venv" ]; then
    echo -e "${RED}❌ Error: Entorno virtual no encontrado${NC}"
    exit 1
fi

source venv/bin/activate

# ============================================
# 4. INSTALAR/ACTUALIZAR DEPENDENCIAS
# ============================================

echo -e "${YELLOW}📦 Instalando dependencias...${NC}"

pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}✅ Dependencias instaladas${NC}"

# ============================================
# 5. MIGRACIÓN DE BASE DE DATOS
# ============================================

echo -e "${YELLOW}🗄️  Verificando migraciones de base de datos...${NC}"

# Verificar duplicados
DUPLICADOS=$(mysql -u root -p hive_mining_db -se "
SELECT COUNT(*) FROM (
    SELECT warehouse_id, rack_id, fila, columna, COUNT(*) as c
    FROM mineros
    WHERE warehouse_id IS NOT NULL 
    GROUP BY warehouse_id, rack_id, fila, columna
    HAVING c > 1
) AS dup;
")

if [ "$DUPLICADOS" -gt 0 ]; then
    echo -e "${RED}⚠️  ADVERTENCIA: Hay $DUPLICADOS posiciones duplicadas${NC}"
    echo "   Revisa manualmente antes de aplicar constraint único"
    read -p "¿Continuar de todas formas? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Aplicar migración
if [ -f "migrations/optimize_concurrency.sql" ]; then
    echo "Aplicando migración de concurrencia..."
    mysql -u root -p hive_mining_db < migrations/optimize_concurrency.sql
    echo -e "${GREEN}✅ Migración aplicada${NC}"
else
    echo -e "${YELLOW}⚠️  Archivo de migración no encontrado (puede ser normal si ya se aplicó)${NC}"
fi

# ============================================
# 6. CREAR DIRECTORIO DE LOGS
# ============================================

echo -e "${YELLOW}📝 Configurando logs...${NC}"

mkdir -p logs
chmod 755 logs

echo -e "${GREEN}✅ Directorio de logs creado${NC}"

# ============================================
# 7. DETENER SERVIDOR ANTERIOR (SI EXISTE)
# ============================================

echo -e "${YELLOW}🛑 Deteniendo servidor anterior...${NC}"

pkill -f gunicorn || echo "   No había servidor corriendo"

# Esperar a que los procesos terminen
sleep 2

# ============================================
# 8. INICIAR SERVIDOR CON GUNICORN
# ============================================

echo -e "${YELLOW}🚀 Iniciando servidor con Gunicorn...${NC}"

gunicorn -c gunicorn_config.py "app:create_app()" &

# Guardar PID
GUNICORN_PID=$!
echo $GUNICORN_PID > logs/gunicorn.pid

# Esperar a que inicie
sleep 5

# Verificar que está corriendo
if ps -p $GUNICORN_PID > /dev/null; then
    echo -e "${GREEN}✅ Servidor iniciado exitosamente (PID: $GUNICORN_PID)${NC}"
else
    echo -e "${RED}❌ Error: El servidor no pudo iniciar${NC}"
    echo "   Revisa logs/gunicorn_error.log"
    exit 1
fi

# ============================================
# 9. HEALTH CHECK
# ============================================

echo -e "${YELLOW}🏥 Verificando salud del servidor...${NC}"

sleep 3

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/ || echo "000")

if [ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "302" ]; then
    echo -e "${GREEN}✅ Servidor respondiendo correctamente (HTTP $HTTP_CODE)${NC}"
else
    echo -e "${RED}❌ Servidor no responde correctamente (HTTP $HTTP_CODE)${NC}"
    echo "   Revisa logs/gunicorn_error.log"
fi

# ============================================
# 10. MOSTRAR INFORMACIÓN
# ============================================

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ DEPLOYMENT COMPLETADO${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo "Información del servidor:"
echo "  • URL: http://localhost:5000"
echo "  • PID: $GUNICORN_PID"
echo "  • Workers: $(grep -c "Worker" logs/gunicorn_error.log 2>/dev/null || echo "N/A")"
echo "  • Logs: logs/gunicorn_error.log"
echo ""
echo "Comandos útiles:"
echo "  • Ver logs: tail -f logs/gunicorn_error.log"
echo "  • Detener: kill $GUNICORN_PID"
echo "  • Reiniciar: kill -HUP $GUNICORN_PID"
echo ""

exit 0
