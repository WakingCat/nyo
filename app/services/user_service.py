"""
User Service - Gestión de Personal
Proporciona funciones para organizar y consultar usuarios por ubicación
"""
from app.models.user import User
from sqlalchemy import or_


class UserService:
    """Servicio para gestión de usuarios y personal"""
    
    @staticmethod
    def get_personnel_by_location(user_role=None, user_dept=None):
        """
        Obtiene personal organizado por WH o Contenedor Hydro
        
        Args:
            user_role: Rol del usuario que solicita (para filtrar)
            user_dept: Departamento del usuario que solicita
            
        Returns:
            dict: {
                'WH': {
                    1: [{'id': 1, 'username': '...', 'role': '...', 'email': '...', 'is_supervisor': bool}, ...],
                    2: [...],
                },
                'Hydro': {
                    1: [...],  # Container 1
                    2: [...],
                }
            }
        """
        # Determinar qué mostrar basado en el rol
        show_wh = True
        show_hydro = True
        
        # Si es Coordinador WH, solo mostrar WH
        if user_role and 'Coordinador' in user_role and user_dept == 'WH':
            show_hydro = False
            
        # Si es Coordinador Hydro, solo mostrar Hydro
        if user_role and 'Coordinador' in user_role and user_dept == 'Hydro':
            show_wh = False
        
        result = {
            'WH': {},
            'Hydro': {}
        }
        
        # Obtener todos los usuarios con asignaciones
        usuarios = User.query.filter(
            or_(
                User.wh_asignados.isnot(None),
                User.containers_asignados.isnot(None)
            )
        ).all()
        
        for usuario in usuarios:
            # Excluir Coordinadores y Site Managers (solo mostrar personal operativo)
            if usuario.role:
                role_name = usuario.role.nombre_puesto
                if 'Coordinador' in role_name or 'Site Manager' in role_name:
                    continue  # Saltar este usuario
            
            user_data = {
                'id': usuario.id,
                'username': usuario.username,
                'role': usuario.role.nombre_puesto if usuario.role else 'Sin Rol',
                'email': usuario.email,
                'is_supervisor': 'Supervisor' in (usuario.role.nombre_puesto if usuario.role else '')
            }
            
            # Procesar asignaciones de WH
            if show_wh and usuario.wh_asignados:
                try:
                    wh_list = [int(x.strip()) for x in usuario.wh_asignados.split(',')]
                    for wh in wh_list:
                        if wh not in result['WH']:
                            result['WH'][wh] = []
                        result['WH'][wh].append(user_data)
                except (ValueError, AttributeError):
                    pass
            
            # Procesar asignaciones de Hydro (containers)
            if show_hydro and usuario.containers_asignados:
                try:
                    container_list = [int(x.strip()) for x in usuario.containers_asignados.split(',')]
                    for container in container_list:
                        if container not in result['Hydro']:
                            result['Hydro'][container] = []
                        result['Hydro'][container].append(user_data)
                except (ValueError, AttributeError):
                    pass
        
        # Ordenar usuarios dentro de cada ubicación (supervisores primero)
        for wh in result['WH']:
            result['WH'][wh].sort(key=lambda x: (not x['is_supervisor'], x['username']))
        
        for container in result['Hydro']:
            result['Hydro'][container].sort(key=lambda x: (not x['is_supervisor'], x['username']))
        
        return result
    
    @staticmethod
    def get_personnel_summary():
        """
        Obtiene un resumen rápido del personal
        
        Returns:
            dict: {'total_supervisores': int, 'total_tecnicos': int, 'total_usuarios': int}
        """
        usuarios = User.query.filter(
            or_(
                User.wh_asignados.isnot(None),
                User.containers_asignados.isnot(None)
            )
        ).all()
        
        supervisores = sum(1 for u in usuarios if u.role and 'Supervisor' in u.role.nombre_puesto)
        total = len(usuarios)
        tecnicos = total - supervisores
        
        return {
            'total_supervisores': supervisores,
            'total_tecnicos': tecnicos,
            'total_usuarios': total
        }


    @staticmethod
    def get_all_personnel(user_role=None, user_dept=None):
        """
        Obtiene lista plana de todo el personal (supervisores y técnicos)
        para la interfaz de asignación, filtrado por permisos.
        """
        # Excluir roles administrativos puros que no se asignan
        query = User.query.filter(User.role_id.isnot(None))
        all_users = query.all()
        
        personnel_list = []
        
        for user in all_users:
            if not user.role: continue
            
            role_name = user.role.nombre_puesto
            dept = user.role.departamento
            
            # FILTRADO DE SEGURIDAD:
            # 1. No mostrar Admins/Coordinadores/Managers en la lista para ser asignados
            if any(x in role_name for x in ['Coordinador', 'Site Manager', 'Manager']):
                continue

            # 2. Si soy Coordinador WH, solo veo gente de WH
            if user_role and 'Coordinador' in user_role and user_dept == 'WH':
                if dept != 'WH': continue
                
            # 3. Si soy Coordinador Hydro, solo veo gente de Hydro
            if user_role and 'Coordinador' in user_role and user_dept == 'Hydro':
                if dept != 'Hydro': continue

            # Preparar datos
            wh_assigned = []
            if user.wh_asignados:
                 wh_assigned = [x.strip() for x in user.wh_asignados.split(',') if x.strip()]
            
            hydro_assigned = []
            if user.containers_asignados:
                 hydro_assigned = [x.strip() for x in user.containers_asignados.split(',') if x.strip()]

            personnel_list.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': role_name,
                'dept': dept,
                'is_supervisor': 'Supervisor' in role_name,
                'wh_assigned': wh_assigned,
                'hydro_assigned': hydro_assigned,
                'display_assignment': UserService._format_assignment(wh_assigned, hydro_assigned)
            })
            
        # Ordenar: Supervisores primero, luego alfabético
        personnel_list.sort(key=lambda x: (not x['is_supervisor'], x['username']))
        return personnel_list

    @staticmethod
    def _format_assignment(wh_list, hydro_list):
        parts = []
        if wh_list:
            parts.append(f"WH: {', '.join(wh_list)}")
        if hydro_list:
            # Resumir si son muchos containers
            if len(hydro_list) > 5:
                parts.append(f"Hydro: {len(hydro_list)} contenedores")
            else:
                parts.append(f"Hydro: {', '.join(hydro_list)}")
        
        return " | ".join(parts) if parts else "Sin asignación"

    @staticmethod
    def update_assignments(user_id, wh_list, container_list):
        """Actualiza las asignaciones de un usuario"""
        user = User.query.get(user_id)
        if not user:
            return False, "Usuario no encontrado"
            
        try:
            # Actualizar WH
            if wh_list is not None:
                user.wh_asignados = ",".join(map(str, wh_list)) if wh_list else None
                
            # Actualizar Hydro
            if container_list is not None:
                user.containers_asignados = ",".join(map(str, container_list)) if container_list else None
                
            from app import db
            db.session.commit()
            return True, "Asignaciones actualizadas"
        except Exception as e:
            from app import db
            db.session.rollback()
            return False, str(e)


# Instancia global del servicio
user_service = UserService()
