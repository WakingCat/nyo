import gspread
import os
import json
from datetime import datetime

class GoogleSheetsService:
    def __init__(self):
        try:
            # OPCIÓN 1: Variable de entorno (para Railway/producción)
            credentials_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
            
            if credentials_json:
                # Parsear JSON de la variable de entorno
                credentials_dict = json.loads(credentials_json)
                self.gc = gspread.service_account_from_dict(credentials_dict)
                print("✅ Google Sheets conectado via variable de entorno.")
            else:
                # OPCIÓN 2: Archivo credentials.json (desarrollo local)
                base_dir = os.path.abspath(os.path.dirname(__file__))
                credentials_path = os.path.join(base_dir, '../../credentials.json')
                self.gc = gspread.service_account(filename=credentials_path)
                print("✅ Google Sheets conectado via credentials.json.")
            
            # Spreadsheet legacy para movimientos y cambio de piezas
            self.spreadsheet_id = '1bk6c3zYVWyDFTGmSmDicYc8EzTECrhgd1nDHfawWkC0'
            # Nueva spreadsheet para RMA WH
            self.rma_spreadsheet_id = '18_S4xJKKtLDlJ23dE8D2QgpHrrjqEmBT31LepkjpM20'
            
        except Exception as e:
            print(f"❌ Error conectando a Google: {e}")
            self.gc = None

    def exportar_rma_aire(self, datos):
        """
        Exporta RMA a la nueva planilla con formato actualizado.
        Columnas: Batch No | WH | Técnico | Date | # PSU | Hashboard | # CB | Problem | 
                  Machine SN | Mac | Location | Model | Model Spec | Warranty | 
                  PSU SN | HB 1 SN | HB 2 SN | HB 3 SN | HB 4 SN | CB SN | Problem Details
        """
        if not self.gc:
            return False

        try:
            sh = self.gc.open_by_key(self.rma_spreadsheet_id)
            ws = sh.worksheet("RMA-WH")  # Hoja específica para RMA de WH
            
            # Determinar qué columna marcar con "1" según el problema
            problem = datos.get('problem', '').upper()
            marca_psu = '1' if 'PSU' in problem else ''
            marca_hb = '1' if 'HASHBOARD' in problem or 'HB' in problem or 'HASH' in problem else ''
            marca_cb = '1' if 'CONTROL' in problem or 'CB' in problem else ''
            
            # Formatear garantía
            garantia = datos.get('garantia_vence', '')
            if garantia and hasattr(garantia, 'strftime'):
                garantia = garantia.strftime('%d/%m/%Y')
            
            # Model Spec solo se llena si es problema de PSU
            model_spec = ''
            if marca_psu == '1':
                th_val = datos.get('th', 0)
                try:
                    th_val = int(float(th_val)) if th_val else 0
                except:
                    th_val = 0
                model_spec = f"(PSU-{datos.get('modelo', '')} {th_val}T) {datos.get('psu_model', '')}"
            
            nueva_fila = [
                str(datos.get('wh', '')),                        # 1. WH
                datos.get('responsable', ''),                    # 2. Técnico
                datos.get('fecha', ''),                          # 3. Date
                marca_psu,                                       # 4. # PSU
                marca_hb,                                        # 5. Hashboard
                marca_cb,                                        # 6. # CB
                datos.get('problem', ''),                        # 7. Problem
                datos.get('sn_fisico', ''),                      # 8. Machine SN
                datos.get('mac', ''),                            # 9. Mac
                f"WH{datos.get('wh', '')} - R{datos.get('rack', '')}",  # 10. Location
                datos.get('modelo', ''),                         # 11. Model
                model_spec,                                      # 12. Model Spec
                garantia,                                        # 13. Warranty
                datos.get('psu_sn', ''),                         # 14. PSU SN
                datos.get('hb1', ''),                            # 15. HB 1 SN
                datos.get('hb2', ''),                            # 16. HB 2 SN
                datos.get('hb3', ''),                            # 17. HB 3 SN
                '',                                              # 18. HB 4 SN (vacío)
                datos.get('cb_sn', ''),                          # 19. CB SN
                datos.get('log', '')                             # 20. Problem Details
            ]
            
            ws.append_row(nueva_fila)
            print(f"✅ [Sheets] RMA exportado: {datos.get('sn_fisico', 'N/A')}")
            return True
        except Exception as e:
            print(f"❌ Error exportando RMA a Sheets: {e}")
            return False

    def exportar_rma_hydro(self, datos):
        """
        Exporta RMA de Hydro a la hoja 'RMA-Hydro'.
        Columnas: FECHA DE DIAGNÓSTICO, RESPONSABLE, CONTENEDOR, RACK, PROBLEM, IP, 
                  SN DIGITAL, SN FÍSICA, MAC, TH, PSU MODEL, PSU SN, 
                  HB1 (CH0) SN, HB2 (CH1) SN, HB3 (CH2) SN, CB SN, DIAGNÓSTICO
        """
        if not self.gc:
            return False

        try:
            sh = self.gc.open_by_key(self.rma_spreadsheet_id)
            ws = sh.worksheet("RMA-Hydro")
            
            # Formatear contenedor: C{num}-{fila}-{columna}
            container = datos.get('container', '')
            fila = datos.get('fila', '')
            columna = datos.get('columna', '')
            contenedor_fmt = f"C{container}-{fila}-{columna}" if container else ''
            
            # Formatear rack (A o B según rack_id)
            rack_id = datos.get('rack', 0)
            try:
                rack_id = int(rack_id)
                rack_letra = 'A' if rack_id % 2 == 1 else 'B'
            except:
                rack_letra = ''
            
            nueva_fila = [
                datos.get('fecha', ''),                    # FECHA DE DIAGNÓSTICO
                datos.get('responsable', ''),              # RESPONSABLE
                contenedor_fmt,                            # CONTENEDOR (C91-4-5)
                rack_letra,                                # RACK (A o B)
                datos.get('problem', ''),                  # PROBLEM
                datos.get('ip', ''),                       # IP
                datos.get('sn_digital', ''),               # SN DIGITAL
                datos.get('sn_fisico', ''),                # SN FÍSICA
                datos.get('mac', ''),                      # MAC
                str(datos.get('th', 0)),                   # TH
                datos.get('psu_model', ''),                # PSU MODEL
                datos.get('psu_sn', ''),                   # PSU SN
                datos.get('hb1', ''),                      # HB1 (CH0) SN
                datos.get('hb2', ''),                      # HB2 (CH1) SN
                datos.get('hb3', ''),                      # HB3 (CH2) SN
                datos.get('cb_sn', ''),                    # CB SN
                datos.get('log', '')                       # DIAGNÓSTICO
            ]
            
            ws.append_row(nueva_fila)
            print(f"✅ [Sheets] RMA Hydro exportado: {datos.get('sn_fisico', 'N/A')}")
            return True
        except Exception as e:
            print(f"❌ Error exportando RMA Hydro a Sheets: {e}")
            return False


    def exportar_movimiento_wh(self, datos):
        """
        Exporta a la hoja 'Movimiento-WH'.
        Columnas: Fecha, SN FÍSICO, ORIGEN, DESTINO, RESPONSABLE, MOTIVO, IP, MAC DIGITAL
        """
        if not self.gc: return False

        try:
            sh = self.gc.open_by_key(self.rma_spreadsheet_id)
            ws = sh.worksheet("Movimiento-WH")
            
            nueva_fila = [
                datos.get('fecha', ''),
                datos.get('sn_fisico', ''),
                datos.get('origen', ''),
                datos.get('destino', ''),
                datos.get('responsable', ''),
                datos.get('motivo', ''),
                datos.get('ip', ''),
                datos.get('mac', '')
            ]
            
            ws.append_row(nueva_fila)
            print(f"✅ [Sheets] Movimiento WH registrado: {datos.get('sn_fisico', 'N/A')}")
            return True
        except Exception as e:
            print(f"❌ [Sheets] Error movimiento WH: {e}")
            return False

    def exportar_movimiento_hydro(self, datos):
        """
        Exporta a la hoja 'Movimiento-Hydro'.
        Columnas: Fecha, SN FÍSICO, ORIGEN, DESTINO, RESPONSABLE, MOTIVO, IP, MAC DIGITAL
        """
        if not self.gc: return False

        try:
            sh = self.gc.open_by_key(self.rma_spreadsheet_id)
            ws = sh.worksheet("Movimiento-Hydro")
            
            nueva_fila = [
                datos.get('fecha', ''),
                datos.get('sn_fisico', ''),
                datos.get('origen', ''),      # Formato C{num} para Hydro
                datos.get('destino', ''),
                datos.get('responsable', ''),
                datos.get('motivo', ''),
                datos.get('ip', ''),
                datos.get('mac', '')
            ]
            
            ws.append_row(nueva_fila)
            print(f"✅ [Sheets] Movimiento Hydro registrado: {datos.get('sn_fisico', 'N/A')}")
            return True
        except Exception as e:
            print(f"❌ [Sheets] Error movimiento Hydro: {e}")
            return False

    def exportar_movimiento(self, datos):
        """
        LEGACY: Exporta a la hoja 'AIRE MOVIMIENTO DE MINERS'.
        Mantener para compatibilidad hacia atrás.
        """
        if not self.gc: return False

        try:
            sh = self.gc.open_by_key(self.spreadsheet_id)
            ws = sh.worksheet("AIRE MOVIMIENTO DE MINERS")
            
            nueva_fila = [
                datos['fecha'],
                datos['sn_fisico'],
                "WH (AIRE)",
                datos['origen'],
                datos['destino'],
                datos['observacion'],
                datos['responsable'],
                datos['motivo'],
                datos['ip'],
                datos['mac'],
                datos['estado']
            ]
            
            ws.append_row(nueva_fila)
            print(f"✅ [Sheets] Movimiento registrado: {datos['sn_fisico']}")
            return True
        except Exception as e:
            print(f"❌ [Sheets] Error movimiento: {e}")
            return False

    def exportar_cambio_piezas(self, datos):
        """Exporta a la hoja 'CAMBIOS DE PIEZAS'."""
        if not self.gc: return False

        try:
            sh = self.gc.open_by_key(self.spreadsheet_id)
            ws = sh.worksheet("CAMBIOS DE PIEZAS")
            
            nueva_fila = [
                "",
                datos['fecha'],
                datos['problema'],
                datos['sn_maquina'],
                datos['mac_digital'],
                datos['ubicacion'],
                datos['modelo'],
                datos['modelo_especifico'],
                datos['cant_coolers'],
                "0",
                datos['psu_sn_viejo'],
                datos['cb_sn_viejo'],
                datos['detalles'],
                datos['tecnico'],
                "", "", "", "",
                datos['ip'],
                datos['estado'],
                ""
            ]
            
            ws.append_row(nueva_fila)
            print(f"✅ [Sheets] Cambio de pieza solicitado: {datos['sn_maquina']}")
            return True
        except Exception as e:
            print(f"❌ [Sheets] Error cambio piezas: {e}")
            return False

    def exportar_diagnostico(self, datos):
        """
        Exporta a la hoja 'Diagnostico' en NUEVA spreadsheet (la misma de RMAs).
        Columnas: Fecha | WH | Ubicación | SN Físico | SN Digital | IP | Falla | Solución | Obs | Técnico
        """
        if not self.gc: return False

        try:
            # USAR rma_spreadsheet_id en lugar de spreadsheet_id
            sh = self.gc.open_by_key(self.rma_spreadsheet_id)
            ws = sh.worksheet("Diagnostico")
            
            ubicacion = f"R{datos.get('rack')} (F{datos.get('fila')}-C{datos.get('columna')})"
            
            nueva_fila = [
                datos.get('fecha'),
                str(datos.get('wh')),
                ubicacion,
                datos.get('sn_fisica'),
                datos.get('sn_digital'),
                datos.get('ip'),
                datos.get('falla'),
                datos.get('solucion'),
                datos.get('observacion'),
                datos.get('tecnico')
            ]
            
            ws.append_row(nueva_fila)
            print(f"✅ [Sheets] Diagnóstico exportado a Planilla Nueva: {datos.get('sn_fisica')}")
            return True
        except Exception as e:
            print(f"❌ [Sheets] Error exportando diagnóstico: {e}")
            return False

    # ============================================
    # IMPORTAR INVENTARIO DEPÓSITO
    # ============================================
    
    def importar_inventario_deposito(self, spreadsheet_id):
        """
        Importa datos de inventario desde la planilla del depósito.
        Retorna lista de piezas con: sn, tipo, modelo_equipo, caja, es_reparado
        """
        if not self.gc:
            return {'status': 'error', 'message': 'No hay conexión con Google Sheets'}
        
        try:
            sh = self.gc.open_by_key(spreadsheet_id)
            todas_las_hojas = sh.worksheets()
            
            piezas = []
            hojas_procesadas = []
            errores = []
            
            # Mapeo de nombres de hojas a tipo y modelo
            mapeo_hojas = {
                'PSU S21+': ('PSU', 'S21+', False),
                'PSU Hydro': ('PSU', 'S21hyd', False),
                'PSU AVALON': ('PSU', 'Avalon', False),
                'PSU BUZZMINER': ('PSU', 'Buzzminer', False),
                'PSU reparado Hydro': ('PSU', 'S21hyd', True),
                'PSU reparado S21+': ('PSU', 'S21+', True),
                'FAN S21+': ('FAN', 'S21+', False),
                'FAN AVALON': ('FAN', 'Avalon', False),
                'FAN BUZZMINER': ('FAN', 'Buzzminer', False),
                'CB S21+ Aéreo Pallet 01': ('CB', 'S21+', False),
                'CB S21+Hydro Pallet 01': ('CB', 'S21hyd', False),
                'Calentador HYDRO': ('CALENTADOR', 'S21hyd', False),
                'CONJUNTO DE DISTRIBUIDOR': ('DISTRIBUIDOR', 'S21hyd', False),
                'PDU': ('PDU', 'General', False),
            }
            
            for hoja in todas_las_hojas:
                nombre_hoja = hoja.title
                
                if nombre_hoja not in mapeo_hojas:
                    continue
                    
                tipo_pieza, modelo_equipo, es_reparado = mapeo_hojas[nombre_hoja]
                
                try:
                    # Obtener todos los valores
                    valores = hoja.get_all_values()
                    
                    # Buscar columnas de SN y Caja
                    if len(valores) < 2:
                        continue
                    
                    headers = valores[0]
                    
                    # Encontrar índices de columnas
                    col_sn = []
                    col_caja = -1
                    col_ubicacion = []
                    
                    for idx, header in enumerate(headers):
                        header_lower = header.lower().strip()
                        if 'sn' in header_lower and 'n°' not in header_lower:
                            col_sn.append(idx)
                        elif 'caja' in header_lower or 'n° de caja' in header_lower.replace('°', ''):
                            col_caja = idx
                        elif 'ubicacion' in header_lower or 'ubicación' in header_lower:
                            col_ubicacion.append(idx)
                    
                    # Si no encontramos columnas SN, intentar detectar por contenido
                    if not col_sn:
                        # Asumir que las columnas después de "N° de Caja" son SN
                        for idx, header in enumerate(headers):
                            if idx > 0 and 'caja' not in header.lower():
                                col_sn.append(idx)
                    
                    # Procesar filas de datos
                    for fila_idx, fila in enumerate(valores[1:], start=2):
                        # Obtener número de caja
                        caja_num = None
                        if col_caja >= 0 and col_caja < len(fila):
                            try:
                                caja_num = int(fila[col_caja])
                            except:
                                caja_num = None
                        
                        # Procesar cada columna de SN
                        for sn_idx in col_sn:
                            if sn_idx >= len(fila):
                                continue
                            
                            sn = str(fila[sn_idx]).strip()
                            
                            # Validar que sea un SN válido (no vacío, no "sin código", etc.)
                            if not sn or len(sn) < 5:
                                continue
                            if sn.lower() in ['sin código', 'sin codigo', 'n/a', '-', 'total']:
                                continue
                            if sn.isdigit() and len(sn) < 6:
                                continue
                            
                            # Determinar ubicación si hay columna
                            ubicacion = 'STOCK'
                            for ub_idx in col_ubicacion:
                                if ub_idx < len(fila):
                                    ub_val = fila[ub_idx].lower().strip()
                                    if ub_val == 'lab':
                                        ubicacion = 'LAB'
                                    elif ub_val == 'stock':
                                        ubicacion = 'STOCK'
                                    elif 'reparado' in ub_val:
                                        ubicacion = 'REPARACION'
                            
                            piezas.append({
                                'sn': sn,
                                'tipo': tipo_pieza,
                                'modelo_equipo': modelo_equipo,
                                'caja_numero': caja_num,
                                'es_reparado': es_reparado,
                                'ubicacion': ubicacion,
                                'hoja_origen': nombre_hoja
                            })
                    
                    hojas_procesadas.append(nombre_hoja)
                    
                except Exception as e:
                    errores.append(f"{nombre_hoja}: {str(e)}")
                    continue
            
            return {
                'status': 'ok',
                'piezas': piezas,
                'hojas_procesadas': hojas_procesadas,
                'errores': errores,
                'total': len(piezas)
            }
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}